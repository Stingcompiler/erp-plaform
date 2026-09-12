"""
HR serializers.

Company scoping is enforced by the viewset (CompanyScopedModelViewSet forces
`company` from the request user and filters every queryset). Relational fields
that point at other company-owned rows (employee, branch, department, position)
are narrowed to the request user's company in `__init__` so a client can't
attach another tenant's row by id. Reviewer/approver identities come from the
request user, never the request body.
"""
from django.utils import timezone
from rest_framework import serializers

from hr.models import (
    Attendance,
    Deduction,
    Employee,
    EmployeeDocument,
    LeaveRequest,
    PerformanceRecord,
    Position,
    SalaryAdvance,
    PayrollRun,
    PayrollEntry,
    WorkPolicy,
    LeaveAllowance,
    LeaveAccrualPolicy,
)


class _CompanyScopedFKMixin:
    scoped_fk_fields = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        company_id = getattr(getattr(request, "user", None), "company_id", None)
        if company_id is None:
            return
        for name in self.scoped_fk_fields:
            field = self.fields.get(name)
            if field is not None and getattr(field, "queryset", None) is not None:
                field.queryset = field.queryset.filter(company_id=company_id)


class PositionSerializer(serializers.ModelSerializer):
    employee_count = serializers.SerializerMethodField()

    def validate_base_salary(self, value):
        if value < 0:
            raise serializers.ValidationError("Salary cannot be negative.")
        return value

    class Meta:
        model = Position
        fields = [
            "id", "title", "description", "base_salary", "is_active",
            "employee_count", "created_at",
        ]
        read_only_fields = ["created_at"]

    def get_employee_count(self, obj):
        return obj.employees.count()


class EmployeeSerializer(_CompanyScopedFKMixin, serializers.ModelSerializer):
    scoped_fk_fields = ("branch", "department", "position")

    def validate_base_salary_override(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("Salary cannot be negative.")
        return value

    status_display = serializers.CharField(source="get_status_display", read_only=True)
    position_title = serializers.CharField(source="position.title", read_only=True, default=None)
    department_name = serializers.CharField(source="department.name", read_only=True, default=None)

    class Meta:
        model = Employee
        fields = [
            "id", "employee_code", "full_name", "email", "phone",
            "branch", "department", "department_name",
            "position", "position_title",
            "base_salary_override",
            "hire_date", "status", "status_display",
            "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class AttendanceSerializer(_CompanyScopedFKMixin, serializers.ModelSerializer):
    scoped_fk_fields = ("employee",)
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)

    def validate_leave_protection(self, employee, day, instance=None):
        if (instance and instance.source_leave_id) or LeaveRequest.objects.filter(
            company_id=employee.company_id, employee=employee,
            status=LeaveRequest.APPROVED, start_date__lte=day, end_date__gte=day,
        ).exists():
            raise serializers.ValidationError("Attendance is protected by approved leave. Use the leave cancellation process.")

    def validate(self, attrs):
        employee = attrs.get("employee", getattr(self.instance, "employee", None))
        day = attrs.get("date", getattr(self.instance, "date", None))
        ids = {employee.pk}
        if self.instance:
            ids.add(self.instance.employee_id)
        list(Employee.objects.select_for_update().filter(pk__in=ids).order_by("pk"))
        if self.instance:
            self.validate_leave_protection(self.instance.employee, self.instance.date, self.instance)
        self.validate_leave_protection(employee, day)
        return attrs

    class Meta:
        model = Attendance
        fields = [
            "id", "employee", "employee_name", "date", "status",
            "check_in", "check_out", "note", "created_at",
        ]
        read_only_fields = ["created_at"]


class LeaveRequestSerializer(_CompanyScopedFKMixin, serializers.ModelSerializer):
    scoped_fk_fields = ("employee",)
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    leave_type_display = serializers.CharField(
        source="get_leave_type_display", read_only=True
    )
    # Uploaded on write (multipart); on read we only expose whether one exists —
    # the file itself is downloaded through the scoped `report` viewset action,
    # never a public media URL (medical reports are sensitive).
    medical_report = serializers.FileField(
        required=False, allow_null=True, write_only=True
    )
    has_report = serializers.SerializerMethodField()

    class Meta:
        model = LeaveRequest
        fields = [
            "id", "employee", "employee_name", "start_date", "end_date",
            "leave_type", "leave_type_display", "reason", "medical_report",
            "has_report", "status", "status_display", "reviewed_at", "created_at",
        ]
        read_only_fields = ["reviewed_at", "created_at"]

    def get_has_report(self, obj):
        return bool(obj.medical_report)

    def validate(self, attrs):
        if "status" in attrs:
            raise serializers.ValidationError({"status": "Use the approval or rejection action."})
        if self.instance and self.instance.status != LeaveRequest.PENDING:
            raise serializers.ValidationError("A decided leave request cannot be edited.")
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and end < start:
            raise serializers.ValidationError("end_date cannot be before start_date.")
        employee = attrs.get("employee", getattr(self.instance, "employee", None))
        if employee:
            # All leave write endpoints run within a transaction. Lock the
            # employee to serialize overlap checks even for the first request.
            employee = Employee.objects.select_for_update().get(pk=employee.pk)
            if employee.status == Employee.STATUS_TERMINATED:
                raise serializers.ValidationError("Cannot request leave for a terminated employee.")
            if employee.hire_date and start and start < employee.hire_date:
                raise serializers.ValidationError("Leave cannot start before the hire date.")
            if start and end:
                overlaps = LeaveRequest.objects.filter(
                    company_id=employee.company_id, employee=employee,
                    status__in=[LeaveRequest.PENDING, LeaveRequest.APPROVED],
                    start_date__lte=end, end_date__gte=start,
                )
                if self.instance:
                    overlaps = overlaps.exclude(pk=self.instance.pk)
                if overlaps.exists():
                    raise serializers.ValidationError("This leave overlaps another pending or approved request.")
        return attrs

    def update(self, instance, validated_data):
        # Stamp the reviewer/time when a request transitions out of pending.
        request = self.context.get("request")
        new_status = validated_data.get("status")
        if new_status and new_status != instance.status and new_status != LeaveRequest.PENDING:
            validated_data["reviewed_at"] = timezone.now()
            if request is not None:
                validated_data["reviewed_by"] = request.user
        return super().update(instance, validated_data)


class LeaveAllowanceSerializer(_CompanyScopedFKMixin, serializers.ModelSerializer):
    scoped_fk_fields = ("employee",)
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    balance = serializers.SerializerMethodField()

    class Meta:
        model = LeaveAllowance
        fields = ["id", "employee", "employee_name", "year", "leave_type", "entitled_days", "carried_days", "note", "balance", "created_at", "updated_at"]
        read_only_fields = ["created_at", "updated_at"]
        validators = []  # Company is forced by the scoped view, not submitted.

    def get_balance(self, obj):
        from hr.leave_balances import balance
        return {key: str(value) for key, value in balance(obj).items()}

    def validate(self, attrs):
        from hr.leave_balances import usage
        employee = attrs.get("employee", getattr(self.instance, "employee", None))
        user = self.context["request"].user
        if getattr(getattr(user, "role", None), "scope_level", None) == "branch" and user.branch_id and employee.branch_id not in (None, user.branch_id):
            raise serializers.ValidationError({"employee": "Employee is outside your branch."})
        Employee.objects.select_for_update().get(pk=employee.pk)
        year = attrs.get("year", getattr(self.instance, "year", None))
        leave_type = attrs.get("leave_type", getattr(self.instance, "leave_type", None))
        if not 1900 <= year <= 9998:
            raise serializers.ValidationError({"year": "Use a year from 1900 to 9998."})
        if self.instance and (employee.pk != self.instance.employee_id or year != self.instance.year or leave_type != self.instance.leave_type):
            raise serializers.ValidationError("Employee, year and leave type cannot be changed on an existing allocation.")
        if LeaveAllowance.objects.filter(company_id=employee.company_id, employee=employee, year=year, leave_type=leave_type).exclude(pk=getattr(self.instance, "pk", None)).exists():
            raise serializers.ValidationError("An allocation already exists for this employee, year and leave type.")
        entitled = attrs.get("entitled_days", getattr(self.instance, "entitled_days", 0))
        carried = attrs.get("carried_days", getattr(self.instance, "carried_days", 0))
        if entitled < 0 or carried < 0:
            raise serializers.ValidationError("Allocated days cannot be negative.")
        if entitled + carried < usage(employee.pk, employee.company_id, year, leave_type):
            raise serializers.ValidationError("The allocation cannot be less than already approved leave.")
        if not str(attrs.get("note", "")).strip():
            raise serializers.ValidationError({"note": "Provide the allocation or adjustment reason."})
        return attrs


class LeaveAccrualPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveAccrualPolicy
        fields = ["id", "leave_type", "annual_days", "minimum_service_months", "prorate_first_year", "carryover_limit", "is_active", "created_at", "updated_at"]
        read_only_fields = ["created_at", "updated_at"]

    def validate(self, attrs):
        request = self.context.get("request")
        company_id = getattr(getattr(request, "user", None), "company_id", None)
        leave_type = attrs.get("leave_type", getattr(self.instance, "leave_type", None))
        if company_id and LeaveAccrualPolicy.objects.filter(
            company_id=company_id, leave_type=leave_type
        ).exclude(pk=getattr(self.instance, "pk", None)).exists():
            raise serializers.ValidationError({"leave_type": "A policy already exists for this leave type."})
        for name in ("annual_days", "carryover_limit"):
            value = attrs.get(name, getattr(self.instance, name, None))
            if value is not None and value < 0:
                raise serializers.ValidationError({name: "Days cannot be negative."})
        return attrs


class PerformanceRecordSerializer(_CompanyScopedFKMixin, serializers.ModelSerializer):
    scoped_fk_fields = ("employee",)
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    reviewer_name = serializers.CharField(
        source="reviewer.full_name", read_only=True, default=None
    )

    class Meta:
        model = PerformanceRecord
        fields = [
            "id", "employee", "employee_name", "review_date", "rating",
            "summary", "reviewer_name", "created_at",
        ]
        read_only_fields = ["created_at"]

    def validate_rating(self, value):
        if not 1 <= value <= 5:
            raise serializers.ValidationError("Rating must be between 1 and 5.")
        return value

    def create(self, validated_data):
        request = self.context.get("request")
        if request is not None:
            validated_data["reviewer"] = request.user
        return super().create(validated_data)


class EmployeeDocumentSerializer(_CompanyScopedFKMixin, serializers.ModelSerializer):
    scoped_fk_fields = ("employee",)

    class Meta:
        model = EmployeeDocument
        fields = [
            "id", "employee", "title", "doc_type", "file_url", "note", "created_at",
        ]
        read_only_fields = ["created_at"]

    def create(self, validated_data):
        request = self.context.get("request")
        if request is not None:
            validated_data["uploaded_by"] = request.user
        return super().create(validated_data)


class SalaryAdvanceSerializer(_CompanyScopedFKMixin, serializers.ModelSerializer):
    scoped_fk_fields = ("employee",)
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    def validate(self, attrs):
        if "status" in attrs:
            raise serializers.ValidationError({"status": "Use the authorised approval or rejection action."})
        if self.instance and self.instance.status != SalaryAdvance.PENDING:
            raise serializers.ValidationError("A decided advance cannot be edited.")
        return attrs

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("An advance must be greater than zero.")
        return value

    class Meta:
        model = SalaryAdvance
        fields = [
            "id", "employee", "employee_name", "amount", "reason",
            "status", "status_display", "reviewed_at", "created_at",
        ]
        read_only_fields = ["reviewed_at", "created_at"]

    def update(self, instance, validated_data):
        request = self.context.get("request")
        new_status = validated_data.get("status")
        if new_status and new_status != instance.status and new_status != SalaryAdvance.PENDING:
            validated_data["reviewed_at"] = timezone.now()
            if request is not None:
                validated_data["reviewed_by"] = request.user
        return super().update(instance, validated_data)


class PayrollEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = PayrollEntry
        fields = ["id", "employee", "employee_name", "department_name", "position_title", "base_salary", "deductions_total", "advances_total", "net_salary"]
        read_only_fields = fields


class PayrollRunSerializer(serializers.ModelSerializer):
    entries = PayrollEntrySerializer(many=True, read_only=True)
    employee_count = serializers.IntegerField(source="entries.count", read_only=True)

    class Meta:
        model = PayrollRun
        fields = ["id", "period", "status", "employee_count", "created_at", "approved_at", "entries"]
        read_only_fields = fields


class WorkPolicySerializer(serializers.ModelSerializer):
    violation_type_display = serializers.CharField(
        source="get_violation_type_display", read_only=True
    )

    class Meta:
        model = WorkPolicy
        fields = [
            "id", "name", "description", "violation_type",
            "violation_type_display", "is_active", "created_at",
        ]
        read_only_fields = ["created_at"]


class DeductionSerializer(_CompanyScopedFKMixin, serializers.ModelSerializer):
    scoped_fk_fields = ("employee", "policy")
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    policy_name = serializers.CharField(source="policy.name", read_only=True, default=None)
    recorded_by_name = serializers.CharField(
        source="recorded_by.full_name", read_only=True, default=None
    )

    class Meta:
        model = Deduction
        fields = [
            "id", "employee", "employee_name", "policy", "policy_name",
            "amount", "note", "date", "recorded_by_name", "created_at",
        ]
        read_only_fields = ["created_at"]

    def create(self, validated_data):
        request = self.context.get("request")
        if request is not None:
            validated_data["recorded_by"] = request.user
        return super().create(validated_data)
