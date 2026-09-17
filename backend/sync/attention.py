"""Attention badge: queued operations a device gave up on."""

from core.attention import TONE_DANGER, register


@register("sync_discarded", "sales", TONE_DANGER)
def discarded_operations(user, since):
    """Sales, receipts or returns that happened at a counter but never made
    it into the books, dropped by a cashier with a reason. Each one needs a
    manager to make the ledger match reality."""
    from core.rbac import can_approve_high_value
    from sync.models import DiscardedOperation

    if not can_approve_high_value(user):
        return 0
    return DiscardedOperation.objects.filter(
        company_id=user.company_id, resolved_at__isnull=True, created_at__gt=since
    ).count()
