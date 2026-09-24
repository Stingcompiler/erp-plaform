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


@register("price-flags", "sales", TONE_WARN)
def unreviewed_price_flags(user, since):
    """Sales an offline till kept below cost or beyond the discount limit
    (logged `pos_price_unapproved`) that no manager has reviewed yet."""
    from core.rbac import can_review_price_flags
    from sales.price_flags import unreviewed_flags

    if not can_review_price_flags(user):
        return 0
    return len(unreviewed_flags(user, since=since))


@register("till", "sales", TONE_WARN)
def closed_shifts_to_review(user, since):
    """Drawers closed since the last look that no manager has signed off.
    Only an approver can sign a count off, so only an approver is nudged."""
    from core.rbac import can_approve_high_value
    from sales.models import CashShift

    if not can_approve_high_value(user):
        return 0
    qs = CashShift.objects.filter(
        company_id=user.company_id,
        status=CashShift.CLOSED,
        reviewed_at__isnull=True,
        closed_at__gt=since,
    ).exclude(opened_by=user)
    return scope_branch(qs, user).count()


@register("quotes", "sales", TONE_INFO)
def new_open_quotes_and_orders(user, since):
    """Quotations and sales orders someone else opened since the last look
    that are still waiting for the next step (send, convert, invoice)."""
    from sales.models import Quotation, SalesOrder

    quotes = Quotation.objects.filter(
        company_id=user.company_id,
        status__in=[Quotation.DRAFT, Quotation.SENT, Quotation.ACCEPTED],
        created_at__gt=since,
    ).exclude(created_by=user)
    orders = SalesOrder.objects.filter(
        company_id=user.company_id,
        status__in=[SalesOrder.DRAFT, SalesOrder.CONFIRMED],
        created_at__gt=since,
    ).exclude(created_by=user)
    return scope_branch(quotes, user).count() + scope_branch(orders, user).count()
