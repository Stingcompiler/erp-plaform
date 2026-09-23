"""Catalogue repricing under inflation.

A Sudanese wholesaler reprices daily: the pound moved, so every shelf price
moves. Two ways to do that in one stroke:

- by rate: products that carry a reference price (USD) get
  ``reference_price × today's rate``; products without one are left alone.
  The cost likewise comes from ``reference_cost`` only — a product without
  one keeps its cost. Deriving it from the sale price's movement is not
  idempotent (a repeated run doubled the cost), so it is never done.
- by percent: every matched product's current price is scaled.

Prices are then rounded to a step the market actually trades in (nobody
charges 84,317 SDG for a sack of sugar), half up.
"""
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework.exceptions import ValidationError

MODE_RATE = "rate"
MODE_PERCENT = "percent"
MODES = (MODE_RATE, MODE_PERCENT)
TARGET_SALE = "sale"
TARGET_COST = "cost"
TARGET_BOTH = "both"
TARGETS = (TARGET_SALE, TARGET_COST, TARGET_BOTH)
# Rounding steps the till can key in: exact cents up to whole thousands.
STEPS = ("0.01", "1", "5", "10", "50", "100", "500", "1000")
SAMPLE_SIZE = 25
CENTS = Decimal("0.01")


def round_to_step(value, step):
    """Round ``value`` to the nearest multiple of ``step`` (half up)."""
    step = Decimal(str(step))
    if step <= 0:
        raise ValidationError({"step": _("The rounding step must be positive.")})
    units = (Decimal(value) / step).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return (units * step).quantize(CENTS)


def _decimal(params, key, required=False):
    raw = params.get(key)
    if raw in (None, ""):
        if required:
            raise ValidationError({key: _("This value is required.")})
        return None
    try:
        return Decimal(str(raw))
    except ArithmeticError:
        raise ValidationError({key: _("Must be a number.")})


def parse_reprice(params, company):
    """Validate a reprice request into plain values; raises ValidationError."""
    mode = params.get("mode") or MODE_RATE
    if mode not in MODES:
        raise ValidationError({"mode": _("Choose rate or percent.")})
    target = params.get("target") or TARGET_SALE
    if target not in TARGETS:
        raise ValidationError({"target": _("Choose sale, cost or both.")})
    step = str(params.get("step") or "1")
    if step not in STEPS:
        raise ValidationError({"step": _("Choose one of %(options)s.") % {
            "options": ", ".join(STEPS),
        }})
    rate = percent = None
    if mode == MODE_RATE:
        rate = _decimal(params, "rate") or company.exchange_rate
        if not rate or rate <= 0:
            raise ValidationError(
                {"rate": _("Record today's exchange rate first, or pass one.")}
            )
    else:
        percent = _decimal(params, "percent", required=True)
        if percent <= Decimal("-100"):
            raise ValidationError({"percent": _("A cut of 100%% or more leaves no price.") % {}})
    category_id = params.get("category") or None
    if category_id is not None:
        try:
            category_id = int(category_id)
        except (TypeError, ValueError):
            raise ValidationError({"category": _("Must be a category id.")})
    return {
        "mode": mode, "target": target, "step": step, "rate": rate,
        "percent": percent, "category_id": category_id,
        "dry_run": str(params.get("dry_run", "")).lower() in ("1", "true", "yes"),
    }


def _new_price(current, reference, opts):
    if opts["mode"] == MODE_RATE:
        if reference is None:
            return None
        return round_to_step(reference * opts["rate"], opts["step"])
    factor = Decimal("1") + opts["percent"] / Decimal("100")
    return round_to_step(current * factor, opts["step"])


def reprice(company, params):
    """Apply (or preview) a reprice over the company's active catalogue.

    Returns ``{"matched", "changed", "skipped", "sample", ...opts}`` where
    ``sample`` is the first rows with before/after prices so the caller can
    show what will happen before committing.
    """
    from inventory.models import Product

    opts = parse_reprice(params, company)
    qs = Product.objects.filter(company=company, is_active=True).order_by("name")
    if opts["category_id"] is not None:
        qs = qs.filter(category_id=opts["category_id"])
    if opts["mode"] == MODE_RATE:
        if opts["target"] == TARGET_COST:
            qs = qs.filter(reference_cost__isnull=False)
        elif opts["target"] == TARGET_SALE:
            qs = qs.filter(reference_price__isnull=False)
        else:
            qs = qs.filter(Q(reference_price__isnull=False) | Q(reference_cost__isnull=False))
    fields = {
        TARGET_SALE: ("sale_price",), TARGET_COST: ("cost_price",),
        TARGET_BOTH: ("sale_price", "cost_price"),
    }[opts["target"]]

    matched = changed = skipped = 0
    sample = []
    updates = []
    for product in qs.iterator(chunk_size=500):
        matched += 1
        new_values = {}
        for field in fields:
            current = getattr(product, field)
            reference = product.reference_cost if field == "cost_price" else product.reference_price
            value = _new_price(current, reference, opts)
            if value is None:
                continue
            if value != current:
                new_values[field] = value
        if not new_values:
            skipped += 1
            continue
        changed += 1
        if len(sample) < SAMPLE_SIZE:
            sample.append({
                "id": product.pk, "sku": product.sku, "name": product.name,
                "reference_price": product.reference_price,
                "reference_cost": product.reference_cost,
                "before": {f: getattr(product, f) for f in fields},
                "after": {f: new_values.get(f, getattr(product, f)) for f in fields},
            })
        updates.append((product, new_values))

    if not opts["dry_run"] and updates:
        now = timezone.now()
        with transaction.atomic():
            for product, new_values in updates:
                for field, value in new_values.items():
                    setattr(product, field, value)
                # updated_at moves so offline tills pull the new prices.
                product.updated_at = now
            Product.objects.bulk_update(
                [p for p, _ in updates], [*fields, "updated_at"], batch_size=500
            )
    return {
        "mode": opts["mode"], "target": opts["target"], "step": opts["step"],
        "rate": opts["rate"], "percent": opts["percent"],
        "category": opts["category_id"], "dry_run": opts["dry_run"],
        "matched": matched, "changed": changed, "skipped": skipped, "sample": sample,
    }
