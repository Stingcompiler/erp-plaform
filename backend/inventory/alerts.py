"""Stock signals a manager should see without opening a report.

Expiring batches and negative balances are computed from the movement
ledger, like every stock figure here. Used by the dashboard (live) and by
the daily Celery scan (audit-logged summary), so both agree by construction.
"""

from datetime import timedelta
from decimal import Decimal

from django.db.models import DecimalField, F, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from inventory.models import Product, StockBatch

ZERO = Decimal("0")
EXPIRY_HORIZON_DAYS = 30


def expiring_batches(company_id, horizon_days=EXPIRY_HORIZON_DAYS, now=None):
    """Batches with stock left that expire within the horizon (or already
    have), soonest first."""
    today = (now or timezone.now()).date()
    return (
        StockBatch.objects.filter(
            company_id=company_id,
            expiry_date__isnull=False,
            expiry_date__lte=today + timedelta(days=horizon_days),
        )
        .annotate(
            remaining=Coalesce(Sum("stock_movements__quantity"), ZERO, output_field=DecimalField())
        )
        .filter(remaining__gt=0)
        .select_related("product")
        .order_by("expiry_date", "lot_number")
    )


def negative_stock(company_id):
    """Products whose ledger balance is below zero anywhere: the price of
    never blocking an offline sale is that someone must reconcile these."""
    return (
        Product.objects.filter(company_id=company_id, is_stock_tracked=True)
        .annotate(
            on_hand=Coalesce(Sum("stock_movements__quantity"), ZERO, output_field=DecimalField())
        )
        .filter(on_hand__lt=0)
        .order_by("on_hand")
    )


def low_stock(company_id):
    return (
        Product.objects.filter(company_id=company_id, is_stock_tracked=True, is_active=True)
        .annotate(
            on_hand=Coalesce(Sum("stock_movements__quantity"), ZERO, output_field=DecimalField())
        )
        .filter(on_hand__lte=F("reorder_level"))
    )
