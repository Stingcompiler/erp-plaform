"""Payable balances computed in SQL — the AP mirror of sales.querysets.

total − supplier payments − debit notes raised against the bill, void bills
excluded. Debit notes not tied to a bill reduce the supplier's balance once
(see Supplier.ap_balance) and are deliberately not attributed here.
"""
from decimal import Decimal

from django.db.models import DecimalField, ExpressionWrapper, F, OuterRef, Subquery, Sum
from django.db.models.functions import Coalesce

MONEY = DecimalField(max_digits=20, decimal_places=2)
ZERO = Decimal("0")


def with_outstanding(qs):
    from purchasing.models import SupplierPayment
    from returns.models import DebitNote

    paid = (
        SupplierPayment.objects.filter(bill_id=OuterRef("pk"))
        .order_by().values("bill_id").annotate(total=Sum("amount")).values("total")
    )
    debited = (
        DebitNote.objects.filter(bill_id=OuterRef("pk"), is_void=False)
        .order_by().values("bill_id").annotate(total=Sum("amount")).values("total")
    )
    outstanding = (
        F("total")
        - Coalesce(Subquery(paid), ZERO, output_field=MONEY)
        - Coalesce(Subquery(debited), ZERO, output_field=MONEY)
    )
    # `outstanding` is what the supplier is still owed in the bill's own
    # currency (payments and notes default to it). Company-level figures —
    # aging, payables due, cash-flow, CFO KPIs — must not add a dollar bill
    # to a pound one, so they read `outstanding_base`, converted at the
    # bill's recorded rate.
    return qs.filter(is_void=False).annotate(
        outstanding=outstanding,
        outstanding_base=ExpressionWrapper(
            outstanding * F("exchange_rate"), output_field=MONEY
        ),
    )


def open_bills(qs):
    return with_outstanding(qs).filter(outstanding__gt=0)


def payable_total(qs):
    """Open payables in the company currency."""
    return open_bills(qs).aggregate(
        t=Coalesce(Sum("outstanding_base"), ZERO, output_field=MONEY)
    )["t"]
