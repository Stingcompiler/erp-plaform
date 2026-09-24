from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.db import transaction
from django.db.models.functions import Coalesce
from django.http import FileResponse, Http404
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError

from core.activity import log_activity
from core.deletion import ArchiveOnDeleteMixin, NoDeleteMixin
from core.permissions import CanApproveSalaryAdvance, PayrollReportAccess
from core.scoping import CompanyScopedModelViewSet
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
from hr.postings import recoverable_advances
from hr.leave_sync import (
    apply_approved_leave,
    attendance_conflicts,
    refresh_employee_leave_statuses,
)
from hr.serializers import (
    AttendanceSerializer,
    DeductionSerializer,
    EmployeeDocumentSerializer,
    EmployeeSerializer,
    LeaveRequestSerializer,
    PerformanceRecordSerializer,
    PositionSerializer,
    SalaryAdvanceSerializer,
    PayrollRunSerializer,
    WorkPolicySerializer,
    LeaveAllowanceSerializer,
    LeaveAccrualPolicySerializer,
)


class PositionViewSet(ArchiveOnDeleteMixin, CompanyScopedModelViewSet):
    queryset = Position.objects.select_related("company").all()
    serializer_class = PositionSerializer
    activity_entity_type = "Position"


class EmployeeViewSet(CompanyScopedModelViewSet):
    queryset = Employee.objects.select_related("company", "branch", "department", "position").all()
    serializer_class = EmployeeSerializer
    activity_entity_type = "Employee"
    branch_field = "branch"
    include_unassigned_branch_rows = False
    # Marking a leaver terminated is the HR officer's own job, and it is
    # reversible — the record and its history stay.
    manager_only_delete = False

    def get_queryset(self):
        qs = super().get_queryset()
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    def perform_destroy(self, instance):
        """People are archived, never deleted — attendance, leave, deductions
        and performance records all point here, and an employee who has left
        still has a payroll history the company must be able to produce.

        Employee has no `is_active` flag, so this marks `status=terminated`
        rather than using ArchiveOnDeleteMixin.
        """
        if instance.status != Employee.STATUS_TERMINATED:
            instance.status = Employee.STATUS_TERMINATED
            instance.save(update_fields=["status"])
            log_activity(
                action="archive",
                request=self.request,
                entity_type=self._entity_type(),
                entity_id=instance.pk,
            )


class AttendanceViewSet(CompanyScopedModelViewSet):
    branch_field = "employee__branch"
    include_unassigned_branch_rows = False
    queryset = Attendance.objects.select_related("company", "employee").all()
    serializer_class = AttendanceSerializer
    activity_entity_type = "Attendance"
    # Clearing a mistyped attendance line is routine HR work, not a
    # supervisory act — and it carries no financial effect on its own.
    manager_only_delete = False

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        Employee.objects.select_for_update().get(pk=instance.employee_id)
        self.get_serializer().validate_leave_protection(instance.employee, instance.date, instance)
        return super().destroy(request, *args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset()
        employee = self.request.query_params.get("employee")
        if employee:
            qs = qs.filter(employee_id=employee)
        date = self.request.query_params.get("date")
        if date:
            qs = qs.filter(date=date)
        start = self.request.query_params.get("start")
        end = self.request.query_params.get("end")
        if start:
            qs = qs.filter(date__gte=start)
        if end:
            qs = qs.filter(date__lte=end)
        return qs

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Days per status for every employee in a month — the register's
        month view. `month` is YYYY-MM; defaults to the current month."""
        month = request.query_params.get("month") or timezone.localdate().strftime("%Y-%m")
        try:
            year, mon = (int(part) for part in month.split("-"))
            first = date(year, mon, 1)
        except (TypeError, ValueError):
            raise ValidationError({"month": _("Use YYYY-MM.")})
        last = (first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        counts = (
            self.get_queryset()
            .filter(date__gte=first, date__lte=last)
            .values("employee_id", "employee__full_name", "status")
            .annotate(days=Count("id"))
        )
        rows = {}
        for row in counts:
            entry = rows.setdefault(
                row["employee_id"],
                {"employee": row["employee_id"], "employee_name": row["employee__full_name"],
                 "present": 0, "absent": 0, "leave": 0, "half_day": 0},
            )
            entry[row["status"]] = row["days"]
        ordered = sorted(rows.values(), key=lambda r: (r["employee_name"] or "").casefold())
        return Response(
            {"month": month, "start": first.isoformat(), "end": last.isoformat(), "rows": ordered}
        )


class LeaveRequestViewSet(CompanyScopedModelViewSet):
    branch_field = "employee__branch"
    include_unassigned_branch_rows = False
    queryset = LeaveRequest.objects.select_related("company", "employee").all()
    serializer_class = LeaveRequestSerializer
    activity_entity_type = "LeaveRequest"
    # A leave request may be withdrawn by whoever handles it.
    manager_only_delete = False
    # Accept multipart so a sick-leave medical report can be uploaded.
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        if self.get_object().status != LeaveRequest.PENDING:
            return Response({"detail": _("A decided leave request cannot be deleted.")}, status=405)
        return super().destroy(request, *args, **kwargs)

    def get_queryset(self):
        if self.action == "list":
            refresh_employee_leave_statuses(self.request.user.company_id)
        qs = super().get_queryset()
        if self.action in ("approve", "reject", "cancel", "update", "partial_update", "destroy"):
            qs = qs.select_related(None).select_for_update()
        status = self.request.query_params.get("status")
        if status:
            qs = qs.filter(status=status)
        leave_type = self.request.query_params.get("leave_type")
        if leave_type:
            qs = qs.filter(leave_type=leave_type)
        employee = self.request.query_params.get("employee")
        if employee:
            qs = qs.filter(employee_id=employee)
        return qs

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self._decide(request, LeaveRequest.APPROVED)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self._decide(request, LeaveRequest.REJECTED)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def cancel(self, request, pk=None):
        leave = self.get_object()
        if leave.status == LeaveRequest.CANCELLED:
            return Response(self.get_serializer(leave).data)
        if leave.status != LeaveRequest.APPROVED:
            raise ValidationError({"detail": _("Only approved leave can be cancelled.")})
        reason = str(request.data.get("reason", "")).strip()
        if not reason or len(reason) > 1000:
            raise ValidationError(
                {"reason": _("Provide a cancellation reason (1–1000 characters).")}
            )
        Employee.objects.select_for_update().get(pk=leave.employee_id)
        if PayrollRun.objects.filter(
            company_id=leave.company_id,
            status=PayrollRun.APPROVED,
            period__gte=leave.start_date.replace(day=1),
            period__lte=leave.end_date.replace(day=1),
        ).exists():
            raise ValidationError(
                {
                    "detail": _(
                        "This leave overlaps approved payroll; "
                        "a payroll correction is required first."
                    ),
                    "code": "approved_payroll",
                }
            )
        rows = Attendance.objects.filter(
            company_id=leave.company_id,
            employee_id=leave.employee_id,
            date__range=(leave.start_date, leave.end_date),
        )
        if rows.exclude(source_leave=leave).exists():
            raise ValidationError(
                {
                    "detail": _(
                        "Legacy or independently recorded attendance "
                        "needs review before cancellation."
                    ),
                    "code": "legacy_attendance",
                }
            )
        snapshot = list(rows.values("id", "date", "status", "note"))
        for row in snapshot:
            row["date"] = row["date"].isoformat()
        rows.delete()
        leave.status = LeaveRequest.CANCELLED
        leave.save(update_fields=["status"])
        refresh_employee_leave_statuses(leave.company_id)
        log_activity(
            action="cancel",
            request=request,
            entity_type="LeaveRequest",
            entity_id=leave.pk,
            metadata={"reason": reason, "attendance_removed": snapshot},
        )
        return Response(self.get_serializer(leave).data)

    @transaction.atomic
    def _decide(self, request, status_value):
        instance = self.get_object()
        if instance.status == status_value:
            return Response(self.get_serializer(instance).data)
        if instance.status != LeaveRequest.PENDING:
            raise ValidationError({"detail": _("This leave request has already been decided.")})
        if status_value == LeaveRequest.APPROVED:
            # Revalidate current employment and overlaps, including legacy rows.
            validator = self.get_serializer(instance, data={}, partial=True)
            validator.is_valid(raise_exception=True)
            from hr.leave_balances import check_leave_balance

            check_leave_balance(instance)
            conflicts = attendance_conflicts(instance)
            if conflicts.exists():
                raise ValidationError(
                    {
                        "detail": _(
                            "Correct existing attendance records before approving this leave."
                        )
                    }
                )
        instance.status = status_value
        instance.reviewed_by = request.user
        instance.reviewed_at = timezone.now()
        instance.save(update_fields=["status", "reviewed_by", "reviewed_at"])
        if status_value == LeaveRequest.APPROVED:
            apply_approved_leave(instance)
        log_activity(
            action="approve" if status_value == LeaveRequest.APPROVED else "reject",
            request=request,
            entity_type="LeaveRequest",
            entity_id=instance.pk,
        )
        return Response(self.get_serializer(instance).data)

    @action(detail=True, methods=["get"])
    def report(self, request, pk=None):
        """Stream the medical report. `get_object` resolves through the
        company-scoped queryset, so a cross-company id 404s — the file is never
        exposed via a public media URL."""
        instance = self.get_object()
        if not instance.medical_report:
            raise Http404
        from hr.serializers import MEDICAL_REPORT_TYPES

        name = instance.medical_report.name.rsplit("/", 1)[-1]
        extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        # Always a download with a fixed, known content type — never sniffed,
        # never rendered inline on the application origin.
        return FileResponse(
            instance.medical_report.open("rb"),
            as_attachment=True,
            filename=name,
            content_type=MEDICAL_REPORT_TYPES.get(extension, "application/octet-stream"),
        )


class LeaveAllowanceViewSet(NoDeleteMixin, CompanyScopedModelViewSet):
    queryset = LeaveAllowance.objects.select_related("employee").all()
    serializer_class = LeaveAllowanceSerializer
    activity_entity_type = "LeaveAllowance"
    branch_field = "employee__branch"
    include_unassigned_branch_rows = False

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action in ("update", "partial_update"):
            qs = qs.select_related(None).select_for_update()
        year = self.request.query_params.get("year")
        if year:
            try:
                year = int(year)
            except (TypeError, ValueError):
                raise ValidationError({"year": _("Invalid year.")})
            qs = qs.filter(year=year)
        return qs

    def perform_create(self, serializer):
        # Employee already carries branch membership; do not pass a nested
        # employee__branch keyword to Model.save via the base branch hook.
        branch_field = self.branch_field
        self.branch_field = None
        try:
            super().perform_create(serializer)
        finally:
            self.branch_field = branch_field


class LeaveAccrualPolicyViewSet(ArchiveOnDeleteMixin, CompanyScopedModelViewSet):
    queryset = LeaveAccrualPolicy.objects.select_related("company").all()
    serializer_class = LeaveAccrualPolicySerializer
    activity_entity_type = "LeaveAccrualPolicy"

    @action(detail=False, methods=["post"])
    @transaction.atomic
    def generate(self, request):
        try:
            year = int(request.data.get("year"))
        except (TypeError, ValueError):
            raise ValidationError({"year": _("Use a valid year.")})
        if not 1900 <= year <= 9998:
            raise ValidationError({"year": _("Use a year from 1900 to 9998.")})
        from hr.leave_balances import carryover, eligible, policy_entitlement

        policies = list(self.get_queryset().filter(is_active=True))
        employees = list(
            Employee.objects.select_for_update()
            .filter(company_id=request.user.company_id)
            .exclude(status=Employee.STATUS_TERMINATED)
        )
        created, skipped, ineligible = 0, 0, 0
        for policy in policies:
            for employee in employees:
                if not eligible(employee, policy, year):
                    ineligible += 1
                    continue
                allowance, made = LeaveAllowance.objects.get_or_create(
                    company_id=policy.company_id,
                    employee=employee,
                    year=year,
                    leave_type=policy.leave_type,
                    defaults={
                        "entitled_days": policy_entitlement(employee, policy, year),
                        "carried_days": carryover(employee, policy, year),
                        "note": f"Generated from leave policy #{policy.pk} for {year}.",
                    },
                )
                created += int(made)
                skipped += int(not made)
        log_activity(
            action="generate",
            request=request,
            entity_type="LeaveAllowance",
            metadata={
                "year": year,
                "created": created,
                "skipped": skipped,
                "ineligible": ineligible,
            },
        )
        return Response(
            {"year": year, "created": created, "skipped": skipped, "ineligible": ineligible}
        )


class SalaryAdvanceViewSet(CompanyScopedModelViewSet):
    branch_field = "employee__branch"
    include_unassigned_branch_rows = False
    queryset = SalaryAdvance.objects.select_related("company", "employee").all()
    serializer_class = SalaryAdvanceSerializer
    activity_entity_type = "SalaryAdvance"

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        """A pending request is just a request and can be withdrawn. Once it is
        approved or rejected it records a decision about money owed, so it stays
        on file."""
        advance = self.get_object()
        if advance.status != SalaryAdvance.PENDING:
            return Response(
                {
                    "detail": _(
                        "A salary advance that has been decided cannot be "
                        "deleted, because it records money owed by the "
                        "employee. Record a repayment instead."
                    )
                },
                status=status.HTTP_405_METHOD_NOT_ALLOWED,
            )
        return super().destroy(request, *args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action in ("approve", "reject", "update", "partial_update", "destroy"):
            qs = qs.select_related(None).select_for_update()
        status = self.request.query_params.get("status")
        if status:
            qs = qs.filter(status=status)
        employee = self.request.query_params.get("employee")
        if employee:
            qs = qs.filter(employee_id=employee)
        return qs

    @action(detail=True, methods=["post"], permission_classes=[CanApproveSalaryAdvance])
    def approve(self, request, pk=None):
        return self._decide(request, SalaryAdvance.APPROVED)

    @action(detail=True, methods=["post"], permission_classes=[CanApproveSalaryAdvance])
    def reject(self, request, pk=None):
        return self._decide(request, SalaryAdvance.REJECTED)

    @transaction.atomic
    def _decide(self, request, status_value):
        instance = self.get_object()
        if instance.status == status_value:
            return Response(self.get_serializer(instance).data)
        if instance.status != SalaryAdvance.PENDING:
            raise ValidationError({"detail": _("This advance has already been decided.")})
        instance.status = status_value
        instance.reviewed_by = request.user
        instance.reviewed_at = timezone.now()
        instance.save(update_fields=["status", "reviewed_by", "reviewed_at"])
        if status_value == SalaryAdvance.APPROVED:
            # Cash leaves the company now; put it on the books now.
            from hr.postings import post_salary_advance_expense

            post_salary_advance_expense(instance, request.user)
        log_activity(
            action="approve" if status_value == SalaryAdvance.APPROVED else "reject",
            request=request,
            entity_type="SalaryAdvance",
            entity_id=instance.pk,
        )
        return Response(self.get_serializer(instance).data)


class PayrollRunViewSet(NoDeleteMixin, CompanyScopedModelViewSet):
    queryset = PayrollRun.objects.select_related("company").prefetch_related("entries").all()
    serializer_class = PayrollRunSerializer
    activity_entity_type = "PayrollRun"
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_permissions(self):
        return [*super().get_permissions(), PayrollReportAccess()]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action in ("refresh", "approve"):
            qs = qs.select_related(None).select_for_update()
        return qs

    @staticmethod
    def _month_bounds(run):
        period = run.period
        return period, date(period.year + (period.month == 12), (period.month % 12) + 1, 1)

    @staticmethod
    def _eligible_employees(run, month_end):
        return (
            Employee.objects.filter(company_id=run.company_id)
            .exclude(status=Employee.STATUS_TERMINATED)
            .filter(Q(hire_date__isnull=True) | Q(hire_date__lt=month_end))
            .select_related("position", "department")
        )

    @staticmethod
    def _month_figures(run, employee, period, month_end):
        """(deductions, advances) this employee's payroll month recovers — the
        one rule used by the draft calculation and the stale-draft check."""
        deductions = (
            Deduction.objects.filter(company_id=run.company_id, employee=employee)
            .filter(
                Q(date__gte=period, date__lt=month_end)
                | Q(
                    date__isnull=True,
                    created_at__date__gte=period,
                    created_at__date__lt=month_end,
                )
            )
            .aggregate(total=Coalesce(Sum("amount"), Decimal("0")))["total"]
        )
        # Same month rule as the posting (company calendar), so the expense
        # subtracts exactly what this entry recovers.
        advances = (
            recoverable_advances(run.company, period)
            .filter(employee=employee)
            .aggregate(total=Coalesce(Sum("amount"), Decimal("0")))["total"]
        )
        return deductions, advances

    def _stale_names(self, run):
        """Employees whose advances or deductions changed since the draft was
        calculated, or who became payable since. Approving such a draft
        booked an advance nobody recovered from salary: an advance approved
        after the draft was calculated simply never came back."""
        period, month_end = self._month_bounds(run)
        entries = {e.employee_id: e for e in run.entries.all()}
        stale = []
        for employee in self._eligible_employees(run, month_end):
            entry = entries.get(employee.pk)
            deductions, advances = self._month_figures(run, employee, period, month_end)
            if entry is None:
                if deductions or advances or employee.base_salary_override or employee.position_id:
                    stale.append(employee.full_name)
            elif entry.deductions_total != deductions or entry.advances_total != advances:
                stale.append(employee.full_name)
        return stale

    def _recalculate_run(self, run):
        """Replace a draft's entries with a fresh monthly payroll snapshot.

        Approved runs are deliberately never passed here: finance approval makes
        their values an auditable record even if an employee's current salary or
        a deduction later changes.
        """
        period, month_end = self._month_bounds(run)
        employees = self._eligible_employees(run, month_end)
        entries = []
        for employee in employees:
            base = employee.base_salary_override
            if base is None:
                base = employee.position.base_salary if employee.position_id else Decimal("0")
            deductions, advances = self._month_figures(run, employee, period, month_end)
            entries.append(
                PayrollEntry(
                    payroll_run=run,
                    employee=employee,
                    employee_name=employee.full_name,
                    department_name=getattr(employee.department, "name", "") or "",
                    position_title=getattr(employee.position, "title", "") or "",
                    base_salary=base,
                    deductions_total=deductions,
                    advances_total=advances,
                    net_salary=max(Decimal("0"), base - deductions - advances),
                )
            )
        with transaction.atomic():
            run.entries.all().delete()
            PayrollEntry.objects.bulk_create(entries)
        # get_object() prefetches the previous draft entries.
        run._prefetched_objects_cache = {}

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        if request.user.company_id is None:
            raise ValidationError({"detail": _("Select a company before creating payroll.")})
        raw_period = request.data.get("period")
        try:
            period = (
                date.fromisoformat(f"{raw_period}-01")
                if len(str(raw_period)) == 7
                else date.fromisoformat(raw_period)
            )
            period = period.replace(day=1)
        except (TypeError, ValueError):
            raise ValidationError({"period": _("Use YYYY-MM for the payroll month.")})
        run, created = PayrollRun.objects.get_or_create(
            company_id=request.user.company_id,
            period=period,
            defaults={"created_by": request.user},
        )
        if not created:
            return Response(self.get_serializer(run).data, status=status.HTTP_200_OK)
        self._recalculate_run(run)
        log_activity(action="create", request=request, entity_type="PayrollRun", entity_id=run.pk)
        return Response(self.get_serializer(run).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def refresh(self, request, pk=None):
        run = self.get_object()
        if run.status != PayrollRun.DRAFT:
            raise ValidationError(
                {"detail": _("An approved payroll is locked and cannot be recalculated.")}
            )
        self._recalculate_run(run)
        log_activity(
            action="recalculate", request=request, entity_type="PayrollRun", entity_id=run.pk
        )
        return Response(self.get_serializer(run).data)

    @action(detail=True, methods=["post"], permission_classes=[CanApproveSalaryAdvance])
    @transaction.atomic
    def approve(self, request, pk=None):
        run = self.get_object()
        if run.status == PayrollRun.DRAFT:
            stale = self._stale_names(run)
            if stale:
                shown = ", ".join(stale[:5]) + ("…" if len(stale) > 5 else "")
                raise ValidationError({
                    "detail": _(
                        "Advances or deductions changed since this payroll was calculated "
                        "(%(names)s). Recalculate it, then approve."
                    ) % {"names": shown},
                    "code": "payroll_stale",
                })
            run.status = PayrollRun.APPROVED
            run.approved_by = request.user
            run.approved_at = timezone.now()
            run.save(update_fields=["status", "approved_by", "approved_at"])
            # Finance approval is the moment payroll becomes a cost: the
            # expense is posted in this same transaction so the income
            # statement and cash-flow views see it, and no approved run can
            # exist without its figure on the books.
            from hr.postings import post_payroll_expense

            post_payroll_expense(run, request.user)
            log_activity(
                action="approve", request=request, entity_type="PayrollRun", entity_id=run.pk
            )
        return Response(self.get_serializer(run).data)


class WorkPolicyViewSet(ArchiveOnDeleteMixin, CompanyScopedModelViewSet):
    """Archived rather than deleted: past deductions cite the policy they were
    issued under, and that citation must keep resolving."""

    queryset = WorkPolicy.objects.select_related("company").all()
    serializer_class = WorkPolicySerializer
    activity_entity_type = "WorkPolicy"


class DeductionViewSet(NoDeleteMixin, CompanyScopedModelViewSet):
    """Tier A: a deduction reduces an employee's pay. Removing one would change
    what the company owes with no record that anything was there."""

    queryset = Deduction.objects.select_related(
        "company", "employee", "policy", "recorded_by"
    ).all()
    serializer_class = DeductionSerializer
    activity_entity_type = "Deduction"
    delete_denied_detail = gettext_lazy(
        "A deduction cannot be deleted because it affects payroll. Record an "
        "offsetting entry if it was issued in error."
    )
    branch_field = "employee__branch"
    include_unassigned_branch_rows = False

    def get_queryset(self):
        qs = super().get_queryset()
        employee = self.request.query_params.get("employee")
        if employee:
            qs = qs.filter(employee_id=employee)
        return qs


class PerformanceRecordViewSet(CompanyScopedModelViewSet):
    branch_field = "employee__branch"
    include_unassigned_branch_rows = False
    queryset = PerformanceRecord.objects.select_related("company", "employee", "reviewer").all()
    serializer_class = PerformanceRecordSerializer
    activity_entity_type = "PerformanceRecord"

    def get_queryset(self):
        qs = super().get_queryset()
        employee = self.request.query_params.get("employee")
        if employee:
            qs = qs.filter(employee_id=employee)
        return qs


class EmployeeDocumentViewSet(CompanyScopedModelViewSet):
    branch_field = "employee__branch"
    include_unassigned_branch_rows = False
    queryset = EmployeeDocument.objects.select_related("company", "employee").all()
    serializer_class = EmployeeDocumentSerializer
    activity_entity_type = "EmployeeDocument"

    def get_queryset(self):
        qs = super().get_queryset()
        employee = self.request.query_params.get("employee")
        if employee:
            qs = qs.filter(employee_id=employee)
        return qs
