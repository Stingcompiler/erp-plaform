"""The price floor and the discount limit (Company.max_discount_percent).

One rule for every document a salesperson prices: a sale at the till, a
quotation and a sales order. No line below cost, and no line sold further
under its list price than the company allows — a typed-down price and the
discounts on top of it add up. Someone without approver rights is refused
with the reason; an approver's override goes to the audit log, and on a
quote or an order it is also recorded on the document so a later step
(quote -> order -> invoice) does not refuse the price again.

Quotes and orders created before this rule (and web orders, priced by the
owner's own settings at /s/<slug>/) carry `price_checked=False`: their
prices are trusted as agreed, as they always were.
"""
from decimal import Decimal

from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework import serializers

from core.activity import log_activity
from core.rbac import can_approve_high_value

CENT = Decimal("0.01")


def _q2(value):
    return Decimal(value).quantize(CENT)


def price_breaches(rows, limit):
    """The rule breaches among `rows`, one dict per priced line:

    sku, cost, units (pieces or packs sold), unit_value (price per unit
    sold), floor (cost of one unit sold), listed (list price of one unit),
    reference (the price the discount is measured from: the list price, or
    an agreed lower one), gross (units x price) and discount (line plus
    ticket discount on it).

    The list price is always allowed, even under a cost that rose since:
    that price is the owner's decision, not the salesperson's."""
    breaches = []
    for row in rows:
        units, unit_value, listed = row["units"], row["unit_value"], row["listed"]
        gross, discount, reference = row["gross"], row["discount"], row["reference"]
        if row["cost"] > 0 and unit_value < row["floor"] and unit_value < listed:
            breaches.append({
                "sku": row["sku"], "rule": "below_cost", "price": str(_q2(unit_value)),
                "list": str(_q2(listed)), "sold": str(_q2(unit_value)),
            })
        if limit is None or units <= 0:
            continue
        net = gross - discount
        if reference > 0:
            # Measured from the list price: a typed-down price (even a free
            # one) and the discounts on top of it add up.
            base = _q2(reference * units)
            given = base - net
        elif gross > 0:
            # No list price (a miscellaneous line): only the discounts.
            base, given = gross, discount
        else:
            continue
        # A cent of slack: a ticket discount is spread in cents.
        if given > 0 and given > _q2(base * limit / 100) + CENT:
            breaches.append({
                "sku": row["sku"], "rule": "discount",
                "percent": str(_q2(given * 100 / base)),
                "list": str(_q2(reference)), "sold": str(_q2(net / units)),
                "typed_price": discount <= 0,
            })
    return breaches


def refuse(breaches, limit):
    """Raise the reason for the first breach, as the till shows it."""
    first = breaches[0]
    if first["rule"] == "below_cost":
        message = _(
            "%(sku)s is priced below the allowed price. Sell it at the list "
            "price, or ask a manager to ring the sale."
        ) % {"sku": first["sku"]}
    elif first.get("typed_price"):
        message = _(
            "%(sku)s is sold %(percent)s%% below its list price of %(list)s, above the "
            "allowed discount of %(limit)s%%. Raise the price, or ask a manager to "
            "ring the sale."
        ) % {
            "sku": first["sku"], "percent": first["percent"], "list": first["list"],
            "limit": _q2(limit),
        }
    else:
        message = _(
            "The discount on %(sku)s is %(percent)s%%, above the allowed "
            "%(limit)s%%. Ask a manager to ring the sale."
        ) % {"sku": first["sku"], "percent": first["percent"], "limit": _q2(limit)}
    raise serializers.ValidationError({"lines": message, "code": "price_rule"})


def check_document_lines(company, lines, user):
    """Quote or order lines, as (product, quantity, unit_price): the breaches
    an approver overrides. Refuses anyone else before anything is written."""
    limit = company.max_discount_percent
    rows = []
    for product, quantity, price in lines:
        cost = product.cost_price or Decimal("0")
        listed = product.sale_price or Decimal("0")
        rows.append({
            "sku": product.sku, "cost": cost, "units": quantity, "unit_value": price,
            "floor": cost, "listed": listed, "reference": listed,
            "gross": _q2(quantity * price), "discount": Decimal("0"),
        })
    breaches = price_breaches(rows, limit)
    if breaches and not can_approve_high_value(user):
        refuse(breaches, limit)
    return breaches


def record_document_check(document, breaches, user, request, action):
    """Mark the quote/order as priced under the rule; an override is
    recorded on it (and audited) so the next step trusts the price."""
    document.price_checked = True
    fields = ["price_checked"]
    if breaches:
        document.price_approved_by = user
        document.price_approved_at = timezone.now()
        fields += ["price_approved_by", "price_approved_at"]
        log_activity(
            action=action, request=request,
            entity_type=type(document).__name__, entity_id=document.pk,
            metadata={
                "breaches": breaches,
                "limit": str(document.company.max_discount_percent),
            },
        )
    document.save(update_fields=fields)
