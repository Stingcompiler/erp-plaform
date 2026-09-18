"""Where HR money meets the books.

Payroll and advances are real cash leaving the company, but an approved
payroll run used to change only a status: the income statement, the
cash-flow report and the forecast — all built from Expense rows — never
saw a salary. These functions post the expense at the moment of finance
approval, inside the approver's transaction, so there is no approved
payroll without its cost on the books and no cost without its approved
document behind it.

Advances are expensed when paid out (approval). A later payroll recovers
them from net pay, so the payroll expense must not drop them again — see
`payroll_expense_amount`.
"""

from decimal import Decimal

from django.db.models import Sum
from django.db.models.functions import Coalesce


def payroll_expense_amount(run):
    """The month's labour cost not yet on the books.

    Gross cost after deductions = Σ(net_salary + advances_total): net pay
    is cash at month end, and a recovered advance was cash paid earlier
    for this month's work. Advances approved *within* this same month were
    already expensed on approval, so they are subtracted; an advance paid
    and recovered in one month therefore nets to zero here and is counted
    exactly once, on its own expense row.
    """
    from hr.models import SalaryAdvance

    totals = run.entries.aggregate(
        net=Coalesce(Sum("net_salary"), Decimal("0")),
        recovered=Coalesce(Sum("advances_total"), Decimal("0")),
    )
    period = run.period
    month_end = period.replace(
        year=period.year + (period.month == 12), month=(period.month % 12) + 1, day=1
    )
    expensed_this_month = SalaryAdvance.objects.filter(
        company_id=run.company_id, status=SalaryAdvance.APPROVED,
        reviewed_at__date__gte=period, reviewed_at__date__lt=month_end,
    ).aggregate(total=Coalesce(Sum("amount"), Decimal("0")))["total"]
    return (totals["net"] + totals["recovered"] - expensed_this_month).quantize(Decimal("0.01"))


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
        date=(advance.reviewed_at or advance.created_at).date(),
        recorded_by=user,
        salary_advance=advance,
    )
