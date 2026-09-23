"""Calendar-day leave usage. Allocations are explicit, not statutory defaults."""

from datetime import date
from decimal import Decimal

from django.utils.translation import gettext as _
from rest_framework.exceptions import ValidationError

from hr.models import LeaveAllowance, LeaveRequest


def days_in_year(start, end, year):
    first, last = max(start, date(year, 1, 1)), min(end, date(year, 12, 31))
    return Decimal(max(0, (last - first).days + 1))


def usage(employee_id, company_id, year, leave_type, status=LeaveRequest.APPROVED, exclude=None):
    requests = LeaveRequest.objects.filter(
        company_id=company_id,
        employee_id=employee_id,
        leave_type=leave_type,
        status=status,
        start_date__lte=date(year, 12, 31),
        end_date__gte=date(year, 1, 1),
    ).exclude(pk=exclude)
    return sum(
        (
            days_in_year(start, end, year)
            for start, end in requests.values_list("start_date", "end_date")
        ),
        Decimal(0),
    )


def balance(allowance):
    used = usage(allowance.employee_id, allowance.company_id, allowance.year, allowance.leave_type)
    pending = usage(
        allowance.employee_id,
        allowance.company_id,
        allowance.year,
        allowance.leave_type,
        LeaveRequest.PENDING,
    )
    total = allowance.entitled_days + allowance.carried_days
    return {
        "total_days": total,
        "used_days": used,
        "pending_days": pending,
        "remaining_days": total - used,
    }


def check_leave_balance(leave):
    # A company can migrate allocations employee by employee. Missing records
    # mean unconfigured, never an invented zero-day statutory entitlement.
    for year in range(leave.start_date.year, leave.end_date.year + 1):
        allowance = LeaveAllowance.objects.filter(
            company_id=leave.company_id,
            employee_id=leave.employee_id,
            year=year,
            leave_type=leave.leave_type,
        ).first()
        if allowance is None:
            continue
        used = usage(leave.employee_id, leave.company_id, year, leave.leave_type, exclude=leave.pk)
        if (
            used + days_in_year(leave.start_date, leave.end_date, year)
            > allowance.entitled_days + allowance.carried_days
        ):
            raise ValidationError(
                {
                    "detail": _("Insufficient configured leave balance."),
                    "code": "insufficient_leave_balance",
                    "year": year,
                }
            )


def add_months(value, months):
    """Calendar addition without another dependency; safe for month-end hires."""
    month = value.month - 1 + months
    year, month = value.year + month // 12, month % 12 + 1
    import calendar

    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


def eligible(employee, policy, year):
    if not employee.hire_date or employee.hire_date > date(year, 12, 31):
        return False
    return add_months(employee.hire_date, policy.minimum_service_months) <= date(year, 12, 31)


def policy_entitlement(employee, policy, year):
    if policy.prorate_first_year and employee.hire_date.year == year:
        start, end = employee.hire_date, date(year, 12, 31)
        days = (end - start).days + 1
        denominator = (date(year + 1, 1, 1) - date(year, 1, 1)).days
        return (policy.annual_days * Decimal(days) / Decimal(denominator)).quantize(Decimal("0.01"))
    return policy.annual_days


def carryover(employee, policy, year):
    previous = LeaveAllowance.objects.filter(
        company_id=employee.company_id,
        employee=employee,
        year=year - 1,
        leave_type=policy.leave_type,
    ).first()
    if not previous:
        return Decimal("0")
    return min(max(Decimal("0"), balance(previous)["remaining_days"]), policy.carryover_limit)
