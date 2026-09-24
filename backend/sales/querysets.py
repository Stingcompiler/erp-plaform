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


def with_ar_balance(customer_qs):
    """Annotate `ar_balance_sql` on a Customer queryset: exactly
    `Customer.ar_balance()` (the sum of every non-void invoice's
    `amount_due()`, credit balances included), in the same query as the
    customers themselves.

    `ar_balance()` walks the invoices with several queries each, so a list
    of 500 customers with 50 invoices apiece cost ~100k queries. Each term
    here is one correlated subquery per customer over the customer's
    non-void invoices — the arithmetic of `with_outstanding`, grouped by
    customer instead of by invoice."""
    from returns.models import CreditNote
    from sales.models import Invoice, Payment, Refund

    totals = _sum_for(Invoice, "customer_id", "total", is_void=False)
    paid = _sum_for(Payment, "invoice__customer_id", invoice__is_void=False)
    credited = _sum_for(
        CreditNote, "invoice__customer_id", is_void=False, invoice__is_void=False
    )
    refunded = _sum_for(
        Refund, "credit_note__invoice__customer_id", credit_note__invoice__is_void=False
    )
    spent = _sum_for(
        Payment, "credit_note__invoice__customer_id",
        method=Payment.STORE_CREDIT, credit_note__invoice__is_void=False,
    )
    return customer_qs.annotate(
        ar_balance_sql=(
            Coalesce(Subquery(totals), ZERO, output_field=MONEY)
            - Coalesce(Subquery(paid), ZERO, output_field=MONEY)
            - Coalesce(Subquery(credited), ZERO, output_field=MONEY)
            + Coalesce(Subquery(refunded), ZERO, output_field=MONEY)
            + Coalesce(Subquery(spent), ZERO, output_field=MONEY)
        )
    )
