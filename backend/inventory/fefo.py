"""First-Expired-First-Out allocation for batch-tracked products.

A pharmacy or grocer (core customers in the target market) has to know which
lot left the shelf, and must not sell an expired one. Until now the POS wrote
a single untracked `sale_out` even for batch-tracked products, so the batch
balances never decreased and the expiry report was fiction.

Allocation reads remaining quantity per batch from the movement ledger (there
is deliberately no stored quantity on a batch) and takes from the soonest
expiry first, skipping expired lots. Whatever the tracked batches cannot
cover is returned as an untracked remainder — the sale still goes through
(Rule #2: offline-first, never block a sale on stock data that may be stale)
and the ledger shows a deficit against no batch, which the negative-stock
report is for.
"""

from decimal import Decimal

from django.db.models import DecimalField, F, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from inventory.models import StockBatch

ZERO = Decimal("0")


def batch_balances(product, warehouse, as_of=None):
    """[(batch, remaining)] for unexpired batches with stock at this
    warehouse, soonest expiry first, undated lots last."""
    today = (as_of or timezone.now()).date()
    rows = (
        StockBatch.objects.filter(product=product, stock_movements__warehouse=warehouse)
        .annotate(
            remaining=Coalesce(
                Sum("stock_movements__quantity"), ZERO, output_field=DecimalField()
            )
        )
        .filter(remaining__gt=0)
        .order_by(F("expiry_date").asc(nulls_last=True), "lot_number")
    )
    return [
        (batch, batch.remaining)
        for batch in rows
        if batch.expiry_date is None or batch.expiry_date >= today
    ]


def allocate_fefo(product, warehouse, quantity, preferred_batch=None, as_of=None):
    """Split `quantity` into [(batch_or_None, qty)].

    `preferred_batch` (a scanned lot) is drawn down first if it has stock and
    is not expired; the rest follows FEFO. The final element carries
    batch=None only when tracked stock cannot cover the sale.
    """
    remaining = Decimal(quantity)
    plan = []
    balances = batch_balances(product, warehouse, as_of=as_of)
    if preferred_batch is not None:
        balances.sort(key=lambda item: 0 if item[0].pk == preferred_batch.pk else 1)
    for batch, available in balances:
        if remaining <= 0:
            break
        take = min(available, remaining)
        plan.append((batch, take))
        remaining -= take
    if remaining > 0:
        plan.append((None, remaining))
    return plan
