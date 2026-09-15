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
    """Products pushed below zero by a movement that ARRIVED since the last
    look. A movement's created_at is business time, so an offline sale
    replayed hours later carries a timestamp older than the manager's last
    visit and would slip past a plain created_at filter — exactly the sale
    that most needs a second look. Its invoice's received_at is the server
    clock, so replayed sales are counted by when they arrived."""
    from django.db.models import Q

    from inventory.alerts import negative_stock
    from inventory.models import StockMovement
    from sales.models import Invoice

    negative_ids = negative_stock(user.company_id).values_list("pk", flat=True)
    arrived = Invoice.objects.filter(
        company_id=user.company_id, received_at__gt=since
    ).values_list("id", flat=True)
    qs = StockMovement.objects.filter(
        Q(created_at__gt=since)
        | Q(reference_type="Invoice", reference_id__in=[str(i) for i in arrived]),
        company_id=user.company_id,
        product_id__in=negative_ids,
        quantity__lt=0,
        **_warehouse_filter(user, ""),
    )
    return qs.values("product_id").distinct().count()
