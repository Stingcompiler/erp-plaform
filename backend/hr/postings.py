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

Recovery is a running balance per employee: everything approved and due by
a payroll month, less what approved payrolls actually recovered. A month
whose net pay cannot absorb the whole advance recovers what it can and the
rest carries to the next month — nothing is written off silently.
"""

from collections import defaultdict
from datetime import date, datetime, time
from decimal import Decimal

from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from core.timezone import company_zone

ZERO = Decimal("0")


def _next_month(period):
    return date(period.year + (period.month == 12), (period.month % 12) + 1, 1)


def company_today(company):
    """Today in the company's own calendar."""
    return timezone.localdate(timezone.now(), company_zone(company))


def advance_paid_on(advance):
    """The day the advance's cash left, in the company's calendar (an
    approval at 00:30 Khartoum time is that day, not UTC's previous one)."""
    moment = advance.reviewed_at or advance.created_at
    return timezone.localdate(moment, company_zone(advance.company))


def recover_period_for(advance):
    """The payroll month that starts recovering an advance approved now:
    its approval month, unless that month's payroll is already approved —
    then the first later month without an approved payroll. An advance
    paid after the month was closed used to be recovered by nobody."""
    from hr.models import PayrollRun

    period = advance_paid_on(advance).replace(day=1)
    approved = set(
        PayrollRun.objects.filter(
            company_id=advance.company_id, status=PayrollRun.APPROVED, period__gte=period
        ).values_list("period", flat=True)
    )
    while period in approved:
        period = _next_month(period)
    return period


def advance_due_q(company, period):
    """Approved advances due for recovery by payroll month `period`: those
    whose recover_period is that month or earlier. Rows approved before
    recover_period existed fall back to their approval month in the
    company's calendar."""
    end = datetime.combine(_next_month(period), time.min, tzinfo=company_zone(company))
    return Q(recover_period__lte=period) | Q(recover_period__isnull=True, reviewed_at__lt=end)


def entry_recovered(entry):
    """What an entry took from net pay (advances_recovered; entries older
    than that column recovered their whole advances_total)."""
    if isinstance(entry, dict):
        value = entry.get("advances_recovered")
        return entry["advances_total"] if value is None else value
    value = entry.advances_recovered
    return entry.advances_total if value is None else value


def _totals(queryset):
    return dict(
        queryset.values("employee_id")
        .annotate(total=Coalesce(Sum("amount"), ZERO))
        .values_list("employee_id", "total")
    )


def advance_balances(company, period, employee_ids, exclude_run_id=None, settle_all=()):
    """{employee_id: advances payroll month `period` must try to recover}.

    Due by the month = approved advances due by then − what approved payrolls
    of earlier months recovered; never more than the employee's whole
    outstanding balance (an approved later month may already have taken
    some), never negative. Employees in `settle_all` — leavers whose last
    month this is — owe their whole outstanding balance."""
    from hr.models import PayrollEntry, PayrollRun, SalaryAdvance

    employee_ids = list(employee_ids)
    if not employee_ids:
        return {}
    advances = SalaryAdvance.objects.filter(
        company_id=company.pk, status=SalaryAdvance.APPROVED, employee_id__in=employee_ids
    )
    lent_all = _totals(advances)
    if not lent_all:
        return {pk: ZERO for pk in employee_ids}
    lent_due = _totals(advances.filter(advance_due_q(company, period)))
    entries = PayrollEntry.objects.filter(
        payroll_run__company_id=company.pk,
        payroll_run__status=PayrollRun.APPROVED,
        employee_id__in=employee_ids,
    )
    if exclude_run_id is not None:
        entries = entries.exclude(payroll_run_id=exclude_run_id)
    taken_all, taken_before = defaultdict(lambda: ZERO), defaultdict(lambda: ZERO)
    for row in entries.values(
        "employee_id", "payroll_run__period", "advances_total", "advances_recovered"
    ):
        amount = entry_recovered(row)
        taken_all[row["employee_id"]] += amount
        if row["payroll_run__period"] < period:
            taken_before[row["employee_id"]] += amount
    balances = {}
    for pk in employee_ids:
        outstanding = lent_all.get(pk, ZERO) - taken_all[pk]
        due = outstanding if pk in settle_all else min(
            lent_due.get(pk, ZERO) - taken_before[pk], outstanding
        )
        balances[pk] = max(ZERO, due)
    return balances


def payroll_expense_amount(run):
    """The cash this payroll run pays out that is not on the books yet.

    Σ(net_salary + recovered) is the month's labour cost; the part of it an
    entry recovers from advances was paid out earlier, as cash, and already
    expensed on its own row when the advance was approved. So each entry
    subtracts exactly what IT recovered (advances_recovered — not what was
    due, a remainder it could not absorb stays owed) and only as far as
    those advances carry their own expense — never the advances of
    employees outside the run.
    """
    from hr.models import SalaryAdvance

    entries = list(
        run.entries.values("employee_id", "net_salary", "advances_total", "advances_recovered")
    )
    if not entries:
        return Decimal("0.00")
    net = sum((e["net_salary"] for e in entries), ZERO)
    recovered = sum((entry_recovered(e) for e in entries), ZERO)
    # Approved advances without their own expense row (history from before
    # postings existed, not yet backfilled): their recovery is not on the
    # books yet and must stay in this run's figure.
    unexpensed = _totals(
        SalaryAdvance.objects.filter(
            company_id=run.company_id, status=SalaryAdvance.APPROVED,
            employee_id__in=[e["employee_id"] for e in entries], expense__isnull=True,
        ).filter(advance_due_q(run.company, run.period))
    )
    already_on_books = sum(
        (
            min(
                entry_recovered(e),
                max(ZERO, e["advances_total"] - unexpensed.get(e["employee_id"], ZERO)),
            )
            for e in entries
        ),
        ZERO,
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
