"""Attention sources for sales: what a cashier, branch manager or owner
should look at next. Scoped like the dashboard — company, then branch for
branch-level roles."""

from django.utils import timezone

from core.attention import TONE_INFO, TONE_WARN, register, scope_branch


def _invoices(user):
    from sales.models import Invoice

    return scope_branch(
        Invoice.objects.filter(company_id=user.company_id, is_void=False), user
    )


@register("sales", "sales", TONE_INFO)
def newly_overdue_invoices(user, since):
    """Invoices whose due date passed after the user last looked and that
    still carry a balance. An invoice 'appears' the day it becomes overdue."""
    from sales.querysets import overdue_invoices

    today = timezone.localdate()
    return overdue_invoices(_invoices(user)).filter(
        due_date__gte=since.date(), due_date__lt=today
    ).count()


@register("debts", "sales", TONE_WARN)
def unverified_transfers(user, since):
    """Bank-transfer payments recorded since the last look that nobody has
    verified yet — the ledger shows them, the bank may not."""
    from sales.models import Payment

    qs = Payment.objects.filter(
        company_id=user.company_id,
        method="bank_transfer",
        verified_at__isnull=True,
        recorded_at__gt=since,
    ).exclude(recorded_by=user)
    return scope_branch(qs, user, field="invoice__branch").count()
