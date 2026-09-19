"""Zakat on trade goods (زكاة عروض التجارة).

The base is what a trader owns for trade on the hawl day: stock at its
selling value (the Zakat Chamber's basis; cost is shown alongside), cash
in the tills, bank balances and collectible receivables, less the debts
that fall due. The rate is 2.5% per lunar year. Nothing here is a fatwa:
the report lays the figures out and states what it counted so the owner
or the Chamber can adjust.
"""
from decimal import Decimal

from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.db.models.functions import Coalesce

ZERO = Decimal("0")
MONEY = DecimalField(max_digits=20, decimal_places=2)
RATE = Decimal("0.025")
DOUBTFUL_AFTER_DAYS = 90
VALUATIONS = ("sale", "cost")


def _sum(qs, expr):
    return qs.aggregate(t=Coalesce(Sum(expr), ZERO, output_field=MONEY))["t"]


def zakat_base(company_id, *, valuation="sale", exclude_doubtful=False):
    from django.utils import timezone

    from inventory.models import Product
    from purchasing.models import Bill
    from purchasing.querysets import payable_total
    from sales.models import CashShift, CompanyBankAccount, Invoice
    from sales.querysets import receivable_total

    if valuation not in VALUATIONS:
        valuation = "sale"
    products = (
        Product.objects.filter(company_id=company_id, is_active=True, is_stock_tracked=True)
        .annotate(on_hand=Coalesce(Sum("stock_movements__quantity"), ZERO))
        .filter(on_hand__gt=0)
    )
    stock_at_sale = _sum(
        products, ExpressionWrapper(F("on_hand") * F("sale_price"), output_field=MONEY)
    )
    stock_at_cost = _sum(
        products, ExpressionWrapper(F("on_hand") * F("cost_price"), output_field=MONEY)
    )
    stock = stock_at_sale if valuation == "sale" else stock_at_cost

    cash_in_tills = sum(
        (shift.expected_cash() for shift in CashShift.objects.filter(
            company_id=company_id, status=CashShift.OPEN,
        )),
        ZERO,
    )
    bank = sum(
        (account.balance() for account in CompanyBankAccount.objects.filter(
            company_id=company_id, is_active=True,
        )),
        ZERO,
    )
    invoices = Invoice.objects.filter(company_id=company_id)
    receivables = receivable_total(invoices)
    cutoff = timezone.localdate() - timezone.timedelta(days=DOUBTFUL_AFTER_DAYS)
    doubtful = receivable_total(invoices.filter(due_date__lt=cutoff))
    counted_receivables = receivables - doubtful if exclude_doubtful else receivables
    payables = payable_total(Bill.objects.filter(company_id=company_id))

    base = stock + cash_in_tills + bank + counted_receivables - payables
    if base < 0:
        base = ZERO
    cents = Decimal("0.01")
    return {
        "valuation": valuation,
        "exclude_doubtful": exclude_doubtful,
        "rate": str(RATE),
        "stock_at_sale": stock_at_sale.quantize(cents),
        "stock_at_cost": stock_at_cost.quantize(cents),
        "stock": stock.quantize(cents),
        "stock_items": products.count(),
        "cash_in_tills": Decimal(cash_in_tills).quantize(cents),
        "bank": Decimal(bank).quantize(cents),
        "receivables": receivables.quantize(cents),
        "doubtful_receivables": doubtful.quantize(cents),
        "counted_receivables": counted_receivables.quantize(cents),
        "payables": payables.quantize(cents),
        "base": base.quantize(cents),
        "zakat": (base * RATE).quantize(cents),
    }
