"""
HR domain models (M6): Position, Employee, Attendance, LeaveRequest,
PerformanceRecord, EmployeeDocument — plus SalaryAdvance, WorkPolicy and
Deduction (HR system expansion).

Every model is company-scoped (Rule #1) through a direct `company` FK so the
shared CompanyScopedModelViewSet filters and forces tenancy uniformly — the
same pattern CRM and every other module uses. Employee optionally links to the
org tree (branch, department) and, where relevant, to a platform `User`.
"""

from decimal import Decimal

from django.conf import settings
from django.db import models


class Position(models.Model):
    """A job title/role within the company (e.g. 'Cashier', 'Store Manager')."""

    company = models.ForeignKey("org.Company", on_delete=models.CASCADE, related_name="positions")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    # Standard salary/wage for the role, used as the default when hiring into it.
    base_salary = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["title"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "title"], name="uniq_position_title_per_company"
            )
        ]

    def __str__(self):
        return self.title


class Employee(models.Model):
    """A person employed by the company. Optionally tied to a login `User`, and
    placed in the org tree via branch/department for branch-scoped visibility."""

    STATUS_ACTIVE = "active"
    STATUS_ON_LEAVE = "on_leave"
    STATUS_TERMINATED = "terminated"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_ON_LEAVE, "On leave"),
        (STATUS_TERMINATED, "Terminated"),
    ]

    company = models.ForeignKey("org.Company", on_delete=models.CASCADE, related_name="employees")
    branch = models.ForeignKey(
        "org.Branch",
        on_delete=models.SET_NULL,
        related_name="employees",
        null=True,
        blank=True,
    )
    department = models.ForeignKey(
        "org.Department",
        on_delete=models.SET_NULL,
        related_name="employees",
        null=True,
        blank=True,
    )
    position = models.ForeignKey(
        Position,
        on_delete=models.SET_NULL,
        related_name="employees",
        null=True,
        blank=True,
    )
    # A negotiated employee salary, when it differs from the default salary for
    # the assigned position.  Null deliberately means "use the position rate".
    base_salary_override = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True
    )
    # Optional link to a platform login account (not every employee logs in).
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="employee_profile",
        null=True,
        blank=True,
    )
    employee_code = models.CharField(max_length=64, blank=True)
    full_name = models.CharField(max_length=255)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=64, blank=True)
    hire_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name


class Attendance(models.Model):
    """One attendance record per employee per day."""

    PRESENT = "present"
    ABSENT = "absent"
    LEAVE = "leave"
    HALF_DAY = "half_day"
    STATUS_CHOICES = [
        (PRESENT, "Present"),
        (ABSENT, "Absent"),
        (LEAVE, "Leave"),
        (HALF_DAY, "Half day"),
    ]

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="attendance_records"
    )
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="attendance")
    date = models.DateField()
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=PRESENT)
    check_in = models.TimeField(null=True, blank=True)
    check_out = models.TimeField(null=True, blank=True)
    note = models.CharField(max_length=255, blank=True)
    source_leave = models.ForeignKey(
        "LeaveRequest",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="generated_attendance",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    # When the current values were decided — the moment the mark was taken
    # on the device for an offline mark, the server's clock for a live
    # write. A late-arriving offline mark taken before this loses to the
    # row (last writer by business time, not by arrival). Null on rows
    # written before it existed; created_at stands in for those.
    recorded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "date"], name="uniq_attendance_per_employee_day"
            )
        ]

    def __str__(self):
        return f"{self.employee_id} {self.date} {self.status}"


def medical_report_path(instance, filename):
    """Namespace uploads by company so tenants never share a directory."""
    return f"leave_reports/company_{instance.company_id}/{filename}"


class LeaveRequest(models.Model):
    """An employee's request for time off, with an approval workflow.

    `leave_type` is a defined category (annual/casual/unpaid/sick/other). A sick
    leave may carry a `medical_report` attachment; downloads are served only
    through the company-scoped viewset, never a public media URL."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (PENDING, "Pending"),
        (APPROVED, "Approved"),
        (REJECTED, "Rejected"),
        (CANCELLED, "Cancelled"),
    ]

    ANNUAL = "annual"
    CASUAL = "casual"
    UNPAID = "unpaid"
    SICK = "sick"
    OTHER = "other"
    TYPE_CHOICES = [
        (ANNUAL, "Annual"),
        (CASUAL, "Casual"),
        (UNPAID, "Unpaid"),
        (SICK, "Sick"),
        (OTHER, "Other"),
    ]

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="leave_requests"
    )
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="leave_requests")
    start_date = models.DateField()
    end_date = models.DateField()
    leave_type = models.CharField(max_length=16, choices=TYPE_CHOICES, default=ANNUAL)
    reason = models.TextField(blank=True)
    # Optional medical report for sick leave. Stored on disk (or S3 when
    # configured) and downloaded only via the scoped viewset action.
    medical_report = models.FileField(upload_to=medical_report_path, null=True, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=PENDING)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="reviewed_leave_requests",
        null=True,
        blank=True,
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Leave<{self.employee_id}: {self.start_date}–{self.end_date}>"


class LeaveAllowance(models.Model):
    """Explicit HR allocation; no country-specific legal entitlement is assumed."""

    company = models.ForeignKey("org.Company", on_delete=models.CASCADE)
    employee = models.ForeignKey(
        Employee, on_delete=models.PROTECT, related_name="leave_allowances"
    )
    year = models.PositiveSmallIntegerField()
    leave_type = models.CharField(max_length=16, choices=LeaveRequest.TYPE_CHOICES)
    entitled_days = models.DecimalField(max_digits=7, decimal_places=2)
    carried_days = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    note = models.CharField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-year", "employee__full_name", "leave_type"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "employee", "year", "leave_type"],
                name="unique_employee_leave_allowance",
            )
        ]


class LeaveAccrualPolicy(models.Model):
    """Company-owned configuration, never a hard-coded statutory entitlement."""

    company = models.ForeignKey("org.Company", on_delete=models.CASCADE)
    leave_type = models.CharField(max_length=16, choices=LeaveRequest.TYPE_CHOICES)
    annual_days = models.DecimalField(max_digits=7, decimal_places=2)
    minimum_service_months = models.PositiveSmallIntegerField(default=0)
    prorate_first_year = models.BooleanField(default=True)
    carryover_limit = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["leave_type"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "leave_type"], name="unique_company_leave_accrual_policy"
            )
        ]


class PerformanceRecord(models.Model):
    """A periodic performance review/rating for an employee."""

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="performance_records"
    )
    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="performance_records"
    )
    review_date = models.DateField()
    # 1–5 star rating; kept as a small int, validated in the serializer.
    rating = models.PositiveSmallIntegerField(default=3)
    summary = models.TextField(blank=True)
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="authored_performance_records",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-review_date"]

    def __str__(self):
        return f"Review<{self.employee_id}: {self.rating}/5>"


class EmployeeDocument(models.Model):
    """Metadata for a document attached to an employee (contract, ID, etc.).

    Stores a reference/URL and metadata rather than the binary — file storage
    integration mirrors the backup object-storage approach and is an infra
    concern, so the model carries the pointer and audit trail now."""

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="employee_documents"
    )
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="documents")
    title = models.CharField(max_length=255)
    doc_type = models.CharField(max_length=64, blank=True)
    file_url = models.URLField(blank=True)
    note = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="uploaded_employee_documents",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.employee_id})"


class SalaryAdvance(models.Model):
    """An employee's request for an advance against future salary, with the same
    pending/approved/rejected approval workflow as leave."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    STATUS_CHOICES = [
        (PENDING, "Pending"),
        (APPROVED, "Approved"),
        (REJECTED, "Rejected"),
    ]

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="salary_advances"
    )
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="salary_advances")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=PENDING)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="reviewed_salary_advances",
        null=True,
        blank=True,
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Advance<{self.employee_id}: {self.amount}>"


class PayrollRun(models.Model):
    """A monthly payroll snapshot produced by HR and approved by finance."""

    DRAFT = "draft"
    APPROVED = "approved"
    STATUS_CHOICES = [(DRAFT, "Draft"), (APPROVED, "Approved")]

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="payroll_runs"
    )
    period = models.DateField(help_text="First day of the payroll month")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=DRAFT)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="created_payroll_runs",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_payroll_runs",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-period"]
        constraints = [
            models.UniqueConstraint(fields=["company", "period"], name="uniq_payroll_run_per_month")
        ]


class PayrollEntry(models.Model):
    """Immutable salary calculation for one employee within a payroll run."""

    payroll_run = models.ForeignKey(PayrollRun, on_delete=models.CASCADE, related_name="entries")
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="payroll_entries")
    employee_name = models.CharField(max_length=255)
    department_name = models.CharField(max_length=255, blank=True)
    position_title = models.CharField(max_length=255, blank=True)
    base_salary = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    deductions_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    advances_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    net_salary = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))

    class Meta:
        ordering = ["employee_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["payroll_run", "employee"], name="uniq_payroll_entry_per_employee"
            )
        ]


class WorkPolicy(models.Model):
    """A workplace rule/policy an employee can violate (misconduct, absence,
    tardiness, …). Deductions reference the policy that was breached."""

    MISCONDUCT = "misconduct"
    ABSENCE = "absence"
    TARDINESS = "tardiness"
    OTHER = "other"
    VIOLATION_CHOICES = [
        (MISCONDUCT, "Misconduct"),
        (ABSENCE, "Absence"),
        (TARDINESS, "Tardiness"),
        (OTHER, "Other"),
    ]

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="work_policies"
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    violation_type = models.CharField(max_length=16, choices=VIOLATION_CHOICES, default=MISCONDUCT)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Deduction(models.Model):
    """A deduction from an employee's salary for breaching a WorkPolicy. Records
    which policy was violated and which HR user logged it (append-only trail)."""

    company = models.ForeignKey("org.Company", on_delete=models.CASCADE, related_name="deductions")
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="deductions")
    policy = models.ForeignKey(
        WorkPolicy,
        on_delete=models.PROTECT,
        related_name="deductions",
        null=True,
        blank=True,
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    note = models.CharField(max_length=255, blank=True)
    date = models.DateField(null=True, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="recorded_deductions",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Deduction<{self.employee_id}: {self.amount}>"
