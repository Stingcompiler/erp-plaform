"""Shared operating figures for finance, dashboard and reporting.

These are document-based reports, not double-entry accounts. Their costing
method must be displayed: standard uses current cost, FIFO/average the ledger.
"""
from decimal import Decimal

from django.db.models import CharField, DecimalField, ExpressionWrapper, F, Func, Q, Sum
from django.db.models.functions import Cast, Coalesce
from django.utils.dateparse import parse_date
from rest_framework.exceptions import ValidationError

ZERO = Decimal("0")
MONEY = DecimalField(max_digits=20, decimal_places=2)


class RealOnSQLite(Func):
    """Force real-number arithmetic on SQLite; a no-op on PostgreSQL.

    SQLite stores a whole-number decimal (115.00, 100.00) as an integer and
    divides two integers as integers (115 / 100 = 1). Casting to a
    DecimalField does not help: Django renders that as CAST(... AS NUMERIC)
    and NUMERIC affinity collapses back to an integer. A REAL, once produced,
    survives every later NUMERIC cast, so wrapping one operand is enough.
    PostgreSQL divides numerics exactly and is left untouched.
    """

    arity = 1
    template = "%(expressions)s"

    def as_sqlite(self, compiler, connection, **extra_context):
        return super().as_sql(
            compiler, connection, template="CAST(%(expressions)s AS REAL)",
            **extra_context,
        )


def date_range(params):
    dates = []
    for key in ("start", "end"):
        raw = params.get(key)
        try:
            value = parse_date(raw) if raw else None
        except (ValueError, TypeError):
            value = None
        if raw and value is None:
            raise ValidationError({key: "Use a valid YYYY-MM-DD date."})
        dates.append(value)
    if all(dates) and dates[0] > dates[1]:
        raise ValidationError({"end": "End date must not precede start date."})
    return dates


def in_range(qs, field, start, end):
    if start:
        qs = qs.filter(**{f"{field}__gte": start})
    if end:
        qs = qs.filter(**{f"{field}__lte": end})
    return qs


def _revenue_terms(company_id, start=None, end=None, branch_id=None):
    """The one revenue formula: invoiced line subtotals, minus what returned
    goods were actually charged, minus price-correction credit notes (net
    of tax). Shared by the income statement and the dashboard so the two
    screens can never show different revenue for the same period."""
    from sales.models import InvoiceLine
    from returns.models import CreditNote, SalesReturnLine

    lines = in_range(InvoiceLine.objects.filter(
        invoice__company_id=company_id, invoice__is_void=False,
    ), "invoice__issued_at__date", start, end)
    returned_lines = in_range(
        SalesReturnLine.objects.filter(sales_return__company_id=company_id),
        "sales_return__created_at__date", start, end,
    )
    notes = in_range(
        CreditNote.objects.filter(
            company_id=company_id, is_void=False, sales_return__isnull=True,
        ).filter(Q(invoice__isnull=True) | Q(invoice__is_void=False)),
        "created_at__date", start, end,
    )
    if branch_id is not None:
        lines = lines.filter(invoice__branch_id=branch_id)
        returned_lines = returned_lines.filter(sales_return__invoice__branch_id=branch_id)
        notes = notes.filter(invoice__branch_id=branch_id)
    gross_sales = lines.aggregate(t=Coalesce(Sum("line_subtotal"), ZERO, output_field=MONEY))["t"]
    # Reverse what was actually charged for the returned units — the line's
    # net subtotal per unit — not the gross list price, which overstates the
    # reversal for any discounted or pack-priced line.
    returned_sales = returned_lines.aggregate(t=Coalesce(Sum(ExpressionWrapper(
        F("quantity") * F("invoice_line__line_subtotal") / F("invoice_line__quantity"),
        output_field=MONEY,
    )), ZERO, output_field=MONEY))["t"]
    # Credit notes that are not the paperwork of a return (price corrections,
    # goodwill) lower what the customer owes and therefore revenue too. Notes
    # that belong to a voided invoice are excluded: the void already removed
    # the invoice's lines from gross sales.
    # RealOnSQLite keeps the ratio a real number on SQLite (115 / 100 would
    # otherwise be integer division = 1, leaving the tax inside the note).
    tax_share = Coalesce(
        RealOnSQLite(F("invoice__total"), output_field=MONEY) / F("invoice__subtotal"),
        Decimal("1"), output_field=MONEY,
    )
    adjustments = notes.annotate(tax_share=tax_share).aggregate(t=Coalesce(Sum(ExpressionWrapper(
        F("amount") / F("tax_share"), output_field=MONEY,
    )), ZERO, output_field=MONEY))["t"]
    revenue = gross_sales - returned_sales - adjustments
    return lines, gross_sales, returned_sales, adjustments, revenue


def net_revenue(company_id, start=None, end=None, branch_id=None):
    """Revenue as the income statement defines it, for any screen."""
    return _revenue_terms(company_id, start, end, branch_id)[4]


def operating_summary(company_id, start=None, end=None, method="standard"):
    from finance.models import Expense
    from inventory.costing import METHODS, company_totals
    from returns.models import SalesReturnLine

    if method not in METHODS:
        raise ValidationError({"method": "Choose standard, average or fifo."})
    lines, gross_sales, returned_sales, adjustments, revenue = _revenue_terms(
        company_id, start, end
    )
    if method == "standard":
        # Cost as it was when the goods left: the sale_out movement carries a
        # unit_cost snapshot. Rows written before the snapshot existed fall
        # back to the product's current cost, which is the old (drifting)
        # behaviour, so historical figures do not vanish, they just stop
        # changing from here on.
        from django.db.models import OuterRef, Subquery
        from inventory.models import StockMovement

        snapshot = StockMovement.objects.filter(
            reference_type="Invoice",
            reference_id=Cast(OuterRef("invoice_id"), CharField()),
            product_id=OuterRef("product_id"),
            movement_type=StockMovement.SALE_OUT,
            unit_cost__isnull=False,
        ).order_by("id").values("unit_cost")[:1]
        cogs = lines.annotate(
            cost_at_sale=Coalesce(Subquery(snapshot), F("product__cost_price"))
        ).aggregate(t=Coalesce(Sum(ExpressionWrapper(
            F("quantity") * F("cost_at_sale"), output_field=MONEY,
        )), ZERO, output_field=MONEY))["t"]
        restocked = in_range(
            SalesReturnLine.objects.filter(
                sales_return__company_id=company_id,
                disposition=SalesReturnLine.RESTOCKED,
            ),
            "restock_movement__created_at__date", start, end,
        ).aggregate(t=Coalesce(Sum(ExpressionWrapper(
            F("quantity") * F("product__cost_price"), output_field=MONEY,
        )), ZERO, output_field=MONEY))["t"]
        cogs -= restocked
    else:
        cogs = company_totals(company_id, method=method, start=start, end=end)["cogs"]
    expenses = in_range(Expense.objects.filter(company_id=company_id), "date", start, end)
    total = expenses.aggregate(t=Coalesce(Sum("amount"), ZERO, output_field=MONEY))["t"]
    categories = [{"category": row["category"], "amount": str(row["amount"])} for row in
                  expenses.values("category").annotate(amount=Sum("amount")).order_by("-amount")]
    cents = Decimal("0.01")
    return {
        "method": method,
        "gross_sales": str(gross_sales.quantize(cents)),
        "sales_returns": str(returned_sales.quantize(cents)),
        "revenue": str(revenue.quantize(cents)),
        "cogs": str(cogs.quantize(cents)), "gross_profit": str((revenue - cogs).quantize(cents)),
        "total_expenses": str(total.quantize(cents)),
        "expenses_by_category": categories, "expense_count": expenses.count(),
        "net_profit": str((revenue - cogs - total).quantize(cents)),
    }
