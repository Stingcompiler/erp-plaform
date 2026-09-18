"""Receivable balances computed in SQL.

`Invoice.amount_due()` is correct but costs three queries per invoice
(payments, credit notes, refunds). Every place that needs balances for MANY
invoices — aging, cash-flow, the debt ledger, the due-receivables scan, the
dashboard — annotates them here instead, so a company with 100k invoices
answers in one query rather than 300k. The arithmetic is identical:
total − payments − credit notes + refunds + credit spent elsewhere,
void invoices excluded.
"""
from decimal import Decimal

from django.db.models import DecimalField, F, OuterRef, Subquery, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

MONEY = DecimalField(max_digits=20, decimal_places=2)
ZERO = Decimal("0")


def _sum_for(model, group_field, amount_field="amount", **filters):
    return (
        model.objects.filter(**{group_field: OuterRef("pk")}, **filters)
        .order_by()
        .values(group_field)
        .annotate(total=Sum(amount_field))
        .values("total")
    )


def with_outstanding(qs):
    """Annotate `outstanding` (what the customer still owes) on an Invoice
    queryset. Void invoices are excluded because their balance is zero by
    definition and they must never count as receivables."""
    from returns.models import CreditNote
    from sales.models import Payment, Refund

    paid = _sum_for(Payment, "invoice_id")
    credited = _sum_for(CreditNote, "invoice_id", is_void=False)
    refunded = _sum_for(Refund, "credit_note__invoice_id")
    # Store credit spent on another invoice leaves this one the same way a
    # refund does: the credit is gone, the balance comes back up.
    spent = _sum_for(Payment, "credit_note__invoice_id", method=Payment.STORE_CREDIT)
    return qs.filter(is_void=False).annotate(
        outstanding=(
            F("total")
            - Coalesce(Subquery(paid), ZERO, output_field=MONEY)
            - Coalesce(Subquery(credited), ZERO, output_field=MONEY)
            + Coalesce(Subquery(refunded), ZERO, output_field=MONEY)
            + Coalesce(Subquery(spent), ZERO, output_field=MONEY)
        )
    )


def open_invoices(qs):
    """Invoices with a positive balance."""
    return with_outstanding(qs).filter(outstanding__gt=0)


def overdue_invoices(qs):
    """Open invoices past their due date, by the company's calendar."""
    return open_invoices(qs).filter(due_date__lt=timezone.localdate())


def receivable_total(qs):
    """Sum of positive balances (a customer in credit does not offset another's debt)."""
    return open_invoices(qs).aggregate(
        t=Coalesce(Sum("outstanding"), ZERO, output_field=MONEY)
    )["t"]
