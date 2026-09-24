"""Where HR money meets the books.

Payroll and advances are real cash leaving the company, but an approved
payroll run used to change only a status: the income statement, the
cash-flow report and the forecast — all built from Expense rows — never
saw a salary. These functions post the expense at the moment of finance
approval, inside the approver's transaction, so there is no approved
payroll without its cost on the books and no cost without its approved
document behind it.

Advances are expensed when paid out (approval), on the day they were paid
in the company's calendar. A payroll that recovers an advance from net pay
must not count it again — see `payroll_expense_amount`.
"""

from datetime import date, datetime, time
from decimal import Decimal

from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from core.timezone import company_zone


def _next_month(period):
    return date(period.year + (period.month == 12), (period.month % 12) + 1, 1)


def recoverable_advances(company, period):
    """The approved advances a payroll month recovers: those approved on a
    day of that month in the company's own calendar.

    The one rule shared by the draft calculation (which snapshots their sum
    onto each PayrollEntry.advances_total) and the posting (which must know
    which of them were already expensed), so both see the same month."""
    from hr.models import SalaryAdvance

    zone = company_zone(company)
    start = datetime.combine(period, time.min, tzinfo=zone)
    end = datetime.combine(_next_month(period), time.min, tzinfo=zone)
    return SalaryAdvance.objects.filter(
        company_id=company.pk, status=SalaryAdvance.APPROVED,
        reviewed_at__gte=start, reviewed_at__lt=end,
    )


def payroll_expense_amount(run):
    """The cash this payroll run pays out that is not on the books yet.

    Σ(net_salary + advances_total) is the month's labour cost; the part of
    it an entry recovers from advances was paid out earlier, as cash, and
    already expensed on its own row when the advance was approved. So each
    entry subtracts exactly what IT recovered (its advances_total) and only
    as far as those advances carry their own expense — never the advances
    of employees outside the run, or approved after the run was calculated
    and therefore not recovered by it.
    """
    entries = list(run.entries.values("employee_id", "net_salary", "advances_total"))
    if not entries:
        return Decimal("0.00")
    net = sum((e["net_salary"] for e in entries), Decimal("0"))
    recovered = sum((e["advances_total"] for e in entries), Decimal("0"))
    expensed = dict(
        recoverable_advances(run.company, run.period)
        .filter(employee_id__in=[e["employee_id"] for e in entries], expense__isnull=False)
        .values("employee_id")
        .annotate(total=Coalesce(Sum("amount"), Decimal("0")))
        .values_list("employee_id", "total")
    )
    already_on_books = sum(
        (min(e["advances_total"], expensed.get(e["employee_id"], Decimal("0")))
         for e in entries),
        Decimal("0"),
    )
    return (net + recovered - already_on_books).quantize(Decimal("0.01"))


def post_payroll_expense(run, user=None):
    """Create the Expense for an approved payroll run; idempotent."""
    from finance.models import Expense

    if getattr(run, "expense", None) is not None:
        return run.expense
    amount = payroll_expense_amount(run)
    if amount <= 0:
        return None
    return Expense.objects.create(
        company_id=run.company_id,
        category=Expense.CATEGORY_PAYROLL,
        description=f"Payroll {run.period:%Y-%m} — {run.entries.count()} employees",
        amount=amount,
        method=Expense.CASH,
        date=run.period,
        recorded_by=user,
        payroll_run=run,
    )


def advance_paid_on(advance):
    """The day the advance's cash left, in the company's calendar (an
    approval at 00:30 Khartoum time is that day, not UTC's previous one)."""
    moment = advance.reviewed_at or advance.created_at
    return timezone.localdate(moment, company_zone(advance.company))


def post_salary_advance_expense(advance, user=None):
    """Create the Expense for an approved salary advance; idempotent."""
    from finance.models import Expense

    if getattr(advance, "expense", None) is not None:
        return advance.expense
    return Expense.objects.create(
        company_id=advance.company_id,
        category=Expense.CATEGORY_SALARY_ADVANCE,
        description=f"Advance — {advance.employee.full_name}",
        amount=advance.amount,
        method=Expense.CASH,
        date=advance_paid_on(advance),
        recorded_by=user,
        salary_advance=advance,
    )
