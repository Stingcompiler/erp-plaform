"""Attention sources for inventory. Negative stock is the one thing here that
cannot wait — an offline sale went through with nothing on the shelf — so it
carries the danger tone; the rest is ordinary replenishment work."""

from datetime import timedelta

from django.utils import timezone

from core.attention import TONE_DANGER, TONE_INFO, register, branch_scope


def _warehouse_filter(user, prefix):
    branch_id = branch_scope(user)
    return {f"{prefix}warehouse__branch_id": branch_id} if branch_id else {}


@register("inventory", "inventory", TONE_INFO)
def batches_newly_expiring(user, since):
    """Batches whose expiry entered the alert horizon since the last look:
    the ones that became urgent, not everything that is."""
    from inventory.alerts import EXPIRY_HORIZON_DAYS
    from inventory.models import StockBatch

    today = timezone.localdate()
    horizon = timedelta(days=EXPIRY_HORIZON_DAYS)
    # Expiry entered the window between `since` and today.
    qs = StockBatch.objects.filter(
        company_id=user.company_id,
        expiry_date__isnull=False,
        expiry_date__lte=today + horizon,
        expiry_date__gt=since.date() + horizon,
    )
    return qs.count()


@register("stock", "inventory", TONE_DANGER)
def negative_stock_movements(user, since):
    """Products pushed below zero by a movement recorded since the last look."""
    from inventory.alerts import negative_stock
    from inventory.models import StockMovement

    negative_ids = negative_stock(user.company_id).values_list("pk", flat=True)
    qs = StockMovement.objects.filter(
        company_id=user.company_id,
        product_id__in=negative_ids,
        quantity__lt=0,
        created_at__gt=since,
        **_warehouse_filter(user, ""),
    )
    return qs.values("product_id").distinct().count()
