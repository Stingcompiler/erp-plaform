"""Zakat on trade goods (زكاة عروض التجارة).

The base is what a trader owns for trade on the hawl day: stock at its
selling value (the Zakat Chamber's basis; cost is shown alongside), cash
on hand (estimated, or entered by the owner), bank balances and
collectible receivables, less the debts that fall due. The rate is 2.5%
per lunar year. Nothing here is a fatwa: the report lays the figures out
and states what it counted so the owner or the Chamber can adjust.
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


def estimated_cash(company_id):
    """The last cash known to be in each cashier's hands: for every person
    who has run a till, their most recent shift — the live expected cash if
    it is still open, the counted cash if it was closed. Summing every
    closed shift would count each day's takings again every day; counting
    only open drawers dropped the cash of everyone who had closed up. Cash
    moved to a safe or banked after a close is not visible here, which is
    why the report lets the owner enter the figure instead."""
    from sales.models import CashShift

    latest = {}
    shifts = CashShift.objects.filter(company_id=company_id).order_by(
        "opened_by_id", "-opened_at", "-id",
    )
    for shift in shifts.iterator():
        latest.setdefault(shift.opened_by_id, shift)
    total = ZERO
    for shift in latest.values():
        if shift.status == CashShift.OPEN:
            total += shift.expected_cash()
        else:
            counted = shift.counted_cash
            if counted is None:
                counted = shift.expected_at_close or ZERO
            total += counted
    return total


def zakat_base(company_id, *, valuation="sale", exclude_doubtful=False, cash_on_hand=None):
    """`cash_on_hand`, when given, is the owner's own count of the cash held
    (tills, safe, pockets) and replaces the estimate."""
    from django.utils import timezone

    from inventory.models import Product
    from purchasing.models import Bill
    from purchasing.querysets import payable_total
    from sales.models import CompanyBankAccount, Invoice
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

    if cash_on_hand is None:
        cash_in_tills = estimated_cash(company_id)
        cash_source = "estimate"
    else:
        cash_in_tills = Decimal(cash_on_hand)
        cash_source = "entered"
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
        # "estimate" (last known cash per cashier) or "entered" by the owner.
        "cash_source": cash_source,
        "bank": Decimal(bank).quantize(cents),
        "receivables": receivables.quantize(cents),
        "doubtful_receivables": doubtful.quantize(cents),
        "counted_receivables": counted_receivables.quantize(cents),
        "payables": payables.quantize(cents),
        "base": base.quantize(cents),
        "zakat": (base * RATE).quantize(cents),
    }
