"""Shared operating figures for finance, dashboard and reporting.

These are document-based reports, not double-entry accounts. Their costing
method must be displayed: standard uses current cost, FIFO/average the ledger.
"""
from decimal import Decimal

from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.db.models.functions import Coalesce
from django.utils.dateparse import parse_date
from rest_framework.exceptions import ValidationError

ZERO = Decimal("0")
MONEY = DecimalField(max_digits=20, decimal_places=2)


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


def operating_summary(company_id, start=None, end=None, method="standard"):
    from finance.models import Expense
    from inventory.costing import METHODS, company_totals
    from sales.models import InvoiceLine
    from returns.models import SalesReturnLine

    if method not in METHODS:
        raise ValidationError({"method": "Choose standard, average or fifo."})
    lines = in_range(InvoiceLine.objects.filter(
        invoice__company_id=company_id, invoice__is_void=False,
    ), "invoice__issued_at__date", start, end)
    gross_sales = lines.aggregate(t=Coalesce(Sum("line_subtotal"), ZERO, output_field=MONEY))["t"]
    returned_lines = in_range(
        SalesReturnLine.objects.filter(sales_return__company_id=company_id),
        "sales_return__created_at__date", start, end,
    )
    returned_sales = returned_lines.aggregate(t=Coalesce(Sum(ExpressionWrapper(
        F("quantity") * F("invoice_line__unit_price"), output_field=MONEY,
    )), ZERO, output_field=MONEY))["t"]
    revenue = gross_sales - returned_sales
    if method == "standard":
        cogs = lines.aggregate(t=Coalesce(Sum(ExpressionWrapper(
            F("quantity") * F("product__cost_price"), output_field=MONEY,
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
