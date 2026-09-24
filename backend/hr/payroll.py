"""The monthly payroll calculation, in one place.

Used by the draft calculation (create/refresh) and by the stale-draft check
at approval, so both apply exactly the same rules:

* who is paid — hired before the month ends, and not terminated before it
  starts (a leaver is paid for their last month, up to termination_date);
* how much — the monthly rate prorated by calendar days employed in the
  month, less approved *unpaid* leave days at monthly / days-in-month each;
* what is taken — the month's deductions, then outstanding advances as far
  as the remaining pay allows (the rest carries to the next month; a
  leaver's last month tries to settle their whole balance).

Attendance "absent" days are counted for HR to see, never deducted here.
"""

from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce

from core.timezone import company_zone
from hr.models import Attendance, Deduction, Employee, LeaveRequest
from hr.postings import ZERO, advance_balances

CENT = Decimal("0.01")


def month_bounds(period):
    """(first day, first day of the next month)."""
    return period, date(period.year + (period.month == 12), (period.month % 12) + 1, 1)


def eligible_employees(company_id, period):
    """Employees payroll month `period` pays."""
    _first, month_end = month_bounds(period)
    return (
        Employee.objects.filter(company_id=company_id)
        .filter(Q(hire_date__isnull=True) | Q(hire_date__lt=month_end))
        .filter(
            Q(termination_date__gte=period)
            | (Q(termination_date__isnull=True) & ~Q(status=Employee.STATUS_TERMINATED))
        )
        .select_related("position", "department")
    )


def monthly_rate(employee):
    if employee.base_salary_override is not None:
        return employee.base_salary_override
    if employee.position_id:
        return employee.position.base_salary
    return ZERO


def _days(start, stop):
    """Calendar days from start to stop inclusive (0 when stop < start)."""
    return max(0, (stop - start).days + 1)


def _unpaid_leave_days(employee, start, stop):
    if stop < start:
        return 0
    days = set()
    leaves = LeaveRequest.objects.filter(
        company_id=employee.company_id,
        employee=employee,
        status=LeaveRequest.APPROVED,
        leave_type=LeaveRequest.UNPAID,
        start_date__lte=stop,
        end_date__gte=start,
    ).values_list("start_date", "end_date")
    for first, last in leaves:
        day = max(first, start)
        while day <= min(last, stop):
            days.add(day)
            day += timedelta(days=1)
    return len(days)


def _deductions(company, employee, period, month_end):
    zone = company_zone(company)
    created_from = datetime.combine(period, time.min, tzinfo=zone)
    created_to = datetime.combine(month_end, time.min, tzinfo=zone)
    return (
        Deduction.objects.filter(company_id=company.pk, employee=employee)
        .filter(
            Q(date__gte=period, date__lt=month_end)
            | Q(date__isnull=True, created_at__gte=created_from, created_at__lt=created_to)
        )
        .aggregate(total=Coalesce(Sum("amount"), ZERO))["total"]
    )


def calculate_month(company, period, exclude_run_id=None):
    """{employee_id: (employee, figures)} for every employee the month pays;
    `figures` holds the PayrollEntry money/day fields."""
    first, month_end = month_bounds(period)
    last = month_end - timedelta(days=1)
    days_in_month = last.day
    employees = list(eligible_employees(company.pk, period))
    leavers = {
        e.pk for e in employees if e.termination_date and e.termination_date <= last
    }
    advances = advance_balances(
        company, period, [e.pk for e in employees],
        exclude_run_id=exclude_run_id, settle_all=leavers,
    )
    absences = dict(
        Attendance.objects.filter(
            company_id=company.pk, status=Attendance.ABSENT, date__gte=first, date__lte=last,
            employee_id__in=[e.pk for e in employees],
        )
        .values("employee_id")
        .annotate(total=Count("id"))
        .values_list("employee_id", "total")
    ) if employees else {}
    result = {}
    for employee in employees:
        monthly = monthly_rate(employee)
        start = max(first, employee.hire_date or first)
        stop = min(last, employee.termination_date or last)
        employed = _days(start, stop)
        unpaid = _unpaid_leave_days(employee, start, stop)
        paid_days = max(0, employed - unpaid)
        if paid_days == days_in_month:
            base = monthly
        else:
            base = (monthly * paid_days / days_in_month).quantize(CENT, rounding=ROUND_HALF_UP)
        deductions = _deductions(company, employee, first, month_end)
        due = advances.get(employee.pk, ZERO)
        recovered = min(due, max(ZERO, base - deductions))
        result[employee.pk] = (employee, {
            "monthly_salary": monthly,
            "days_employed": employed,
            "unpaid_leave_days": unpaid,
            "absent_days": absences.get(employee.pk, 0),
            "base_salary": base,
            "deductions_total": deductions,
            "advances_total": due,
            "advances_recovered": recovered,
            "net_salary": max(ZERO, base - deductions - recovered),
        })
    return result
