"""Payable balances computed in SQL — the AP mirror of sales.querysets.

total − supplier payments − debit notes raised against the bill, void bills
excluded. Debit notes not tied to a bill reduce the supplier's balance once
(see Supplier.ap_balance) and are deliberately not attributed here.
"""
from decimal import Decimal

from django.db.models import DecimalField, F, OuterRef, Subquery, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

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
    return qs.filter(is_void=False).annotate(
        outstanding=(
            F("total")
            - Coalesce(Subquery(paid), ZERO, output_field=MONEY)
            - Coalesce(Subquery(debited), ZERO, output_field=MONEY)
        )
    )


def open_bills(qs):
    return with_outstanding(qs).filter(outstanding__gt=0)


def overdue_bills(qs):
    return open_bills(qs).filter(due_date__lt=timezone.localdate())


def payable_total(qs):
    return open_bills(qs).aggregate(
        t=Coalesce(Sum("outstanding"), ZERO, output_field=MONEY)
    )["t"]
