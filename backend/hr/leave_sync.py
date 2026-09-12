"""Keep approved leave, attendance, and the employee status consistent."""

from datetime import date, timedelta

from hr.models import Attendance, Employee, LeaveRequest


def leave_dates(leave):
    current = leave.start_date
    while current <= leave.end_date:
        yield current
        current += timedelta(days=1)


def attendance_conflicts(leave):
    """Existing present/absent records need correction before leave approval."""
    return Attendance.objects.filter(
        company_id=leave.company_id,
        employee_id=leave.employee_id,
        date__range=(leave.start_date, leave.end_date),
    ).exclude(status=Attendance.LEAVE)


def apply_approved_leave(leave):
    """Create the leave attendance entries after an approval decision."""
    for day in leave_dates(leave):
        Attendance.objects.get_or_create(
            company_id=leave.company_id,
            employee_id=leave.employee_id,
            date=day,
            defaults={"status": Attendance.LEAVE, "note": "Approved leave", "source_leave": leave},
        )
    refresh_employee_leave_statuses(leave.company_id)


def refresh_employee_leave_statuses(company_id, on_date=None):
    """Mark currently absent staff as on leave and restore them when leave ends."""
    on_date = on_date or date.today()
    on_leave_ids = set(
        LeaveRequest.objects.filter(
            company_id=company_id,
            status=LeaveRequest.APPROVED,
            start_date__lte=on_date,
            end_date__gte=on_date,
        ).values_list("employee_id", flat=True)
    )
    employees = Employee.objects.filter(company_id=company_id).exclude(
        status=Employee.STATUS_TERMINATED
    )
    employees.filter(pk__in=on_leave_ids).exclude(
        status=Employee.STATUS_ON_LEAVE
    ).update(status=Employee.STATUS_ON_LEAVE)
    employees.exclude(pk__in=on_leave_ids).filter(
        status=Employee.STATUS_ON_LEAVE
    ).update(status=Employee.STATUS_ACTIVE)


def sync_approved_leave_attendance(company_id=None):
    """Backfill attendance for approved leave created before this linkage existed."""
    leaves = LeaveRequest.objects.filter(status=LeaveRequest.APPROVED)
    if company_id is not None:
        leaves = leaves.filter(company_id=company_id)
    companies = set()
    for leave in leaves.select_related("employee"):
        if not attendance_conflicts(leave).exists():
            apply_approved_leave(leave)
        companies.add(leave.company_id)
    for current_company_id in companies:
        refresh_employee_leave_statuses(current_company_id)
