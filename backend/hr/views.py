from datetime import date
from decimal import Decimal

from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.http import FileResponse, Http404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError

from core.activity import log_activity
from core.deletion import ArchiveOnDeleteMixin, NoDeleteMixin
from core.permissions import CanApproveSalaryAdvance
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
)
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
)


class PositionViewSet(ArchiveOnDeleteMixin, CompanyScopedModelViewSet):
    queryset = Position.objects.select_related("company").all()
    serializer_class = PositionSerializer
    activity_entity_type = "Position"


class EmployeeViewSet(CompanyScopedModelViewSet):
    queryset = Employee.objects.select_related(
        "company", "branch", "department", "position"
    ).all()
    serializer_class = EmployeeSerializer
    activity_entity_type = "Employee"
    branch_field = "branch"
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
    queryset = Attendance.objects.select_related("company", "employee").all()
    serializer_class = AttendanceSerializer
    activity_entity_type = "Attendance"
    # Clearing a mistyped attendance line is routine HR work, not a
    # supervisory act — and it carries no financial effect on its own.
    manager_only_delete = False

    def get_queryset(self):
        qs = super().get_queryset()
        employee = self.request.query_params.get("employee")
        if employee:
            qs = qs.filter(employee_id=employee)
        date = self.request.query_params.get("date")
        if date:
            qs = qs.filter(date=date)
        return qs


class LeaveRequestViewSet(CompanyScopedModelViewSet):
    queryset = LeaveRequest.objects.select_related("company", "employee").all()
    serializer_class = LeaveRequestSerializer
    activity_entity_type = "LeaveRequest"
    # A leave request may be withdrawn by whoever handles it.
    manager_only_delete = False
    # Accept multipart so a sick-leave medical report can be uploaded.
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def get_queryset(self):
        refresh_employee_leave_statuses(self.request.user.company_id)
        qs = super().get_queryset()
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

    def _decide(self, request, status_value):
        instance = self.get_object()
        if status_value == LeaveRequest.APPROVED:
            conflicts = attendance_conflicts(instance)
            if conflicts.exists():
                raise ValidationError({
                    "detail": "Correct existing attendance records before approving this leave."
                })
        serializer = self.get_serializer(
            instance, data={"status": status_value}, partial=True
        )
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        if status_value == LeaveRequest.APPROVED:
            apply_approved_leave(instance)
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def report(self, request, pk=None):
        """Stream the medical report. `get_object` resolves through the
        company-scoped queryset, so a cross-company id 404s — the file is never
        exposed via a public media URL."""
        instance = self.get_object()
        if not instance.medical_report:
            raise Http404
        return FileResponse(instance.medical_report.open("rb"))


class SalaryAdvanceViewSet(CompanyScopedModelViewSet):
    queryset = SalaryAdvance.objects.select_related("company", "employee").all()
    serializer_class = SalaryAdvanceSerializer
    activity_entity_type = "SalaryAdvance"

    def destroy(self, request, *args, **kwargs):
        """A pending request is just a request and can be withdrawn. Once it is
        approved or rejected it records a decision about money owed, so it stays
        on file."""
        advance = self.get_object()
        if advance.status != SalaryAdvance.PENDING:
            return Response(
                {
                    "detail": (
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

    def _decide(self, request, status_value):
        instance = self.get_object()
        serializer = self.get_serializer(
            instance, data={"status": status_value}, partial=True
        )
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)


class PayrollRunViewSet(CompanyScopedModelViewSet):
    queryset = PayrollRun.objects.select_related("company").prefetch_related("entries").all()
    serializer_class = PayrollRunSerializer
    activity_entity_type = "PayrollRun"

    def create(self, request, *args, **kwargs):
        raw_period = request.data.get("period")
        try:
            period = date.fromisoformat(f"{raw_period}-01") if len(str(raw_period)) == 7 else date.fromisoformat(raw_period)
            period = period.replace(day=1)
        except (TypeError, ValueError):
            raise ValidationError({"period": "Use YYYY-MM for the payroll month."})
        run, created = PayrollRun.objects.get_or_create(
            company_id=request.user.company_id, period=period,
            defaults={"created_by": request.user},
        )
        if not created:
            return Response(self.get_serializer(run).data, status=status.HTTP_200_OK)
        month_end = date(period.year + (period.month == 12), (period.month % 12) + 1, 1)
        employees = Employee.objects.filter(company_id=request.user.company_id).exclude(status=Employee.STATUS_TERMINATED).select_related("position", "department")
        entries = []
        for employee in employees:
            base = employee.position.base_salary if employee.position_id else Decimal("0")
            # Earlier deductions did not require an explicit effective date.
            # Treat those as belonging to the month in which HR recorded them,
            # while keeping dated deductions tied to their stated payroll month.
            deductions = Deduction.objects.filter(
                company_id=request.user.company_id, employee=employee
            ).filter(
                Q(date__gte=period, date__lt=month_end)
                | Q(date__isnull=True, created_at__date__gte=period, created_at__date__lt=month_end)
            ).aggregate(total=Coalesce(Sum("amount"), Decimal("0")))["total"]
            advances = SalaryAdvance.objects.filter(company_id=request.user.company_id, employee=employee, status=SalaryAdvance.APPROVED, reviewed_at__date__gte=period, reviewed_at__date__lt=month_end).aggregate(total=Coalesce(Sum("amount"), Decimal("0")))["total"]
            entries.append(PayrollEntry(payroll_run=run, employee=employee, employee_name=employee.full_name, department_name=getattr(employee.department, "name", "") or "", position_title=getattr(employee.position, "title", "") or "", base_salary=base, deductions_total=deductions, advances_total=advances, net_salary=max(Decimal("0"), base - deductions - advances)))
        PayrollEntry.objects.bulk_create(entries)
        return Response(self.get_serializer(run).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], permission_classes=[CanApproveSalaryAdvance])
    def approve(self, request, pk=None):
        run = self.get_object()
        if run.status == PayrollRun.DRAFT:
            run.status = PayrollRun.APPROVED
            run.approved_by = request.user
            run.approved_at = timezone.now()
            run.save(update_fields=["status", "approved_by", "approved_at"])
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
    delete_denied_detail = (
        "A deduction cannot be deleted because it affects payroll. Record an "
        "offsetting entry if it was issued in error."
    )

    def get_queryset(self):
        qs = super().get_queryset()
        employee = self.request.query_params.get("employee")
        if employee:
            qs = qs.filter(employee_id=employee)
        return qs


class PerformanceRecordViewSet(CompanyScopedModelViewSet):
    queryset = PerformanceRecord.objects.select_related(
        "company", "employee", "reviewer"
    ).all()
    serializer_class = PerformanceRecordSerializer
    activity_entity_type = "PerformanceRecord"

    def get_queryset(self):
        qs = super().get_queryset()
        employee = self.request.query_params.get("employee")
        if employee:
            qs = qs.filter(employee_id=employee)
        return qs


class EmployeeDocumentViewSet(CompanyScopedModelViewSet):
    queryset = EmployeeDocument.objects.select_related("company", "employee").all()
    serializer_class = EmployeeDocumentSerializer
    activity_entity_type = "EmployeeDocument"

    def get_queryset(self):
        qs = super().get_queryset()
        employee = self.request.query_params.get("employee")
        if employee:
            qs = qs.filter(employee_id=employee)
        return qs
