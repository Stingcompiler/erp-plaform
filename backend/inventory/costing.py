"""
Inventory costing (enhancement beyond M9's standard-cost-only reports).

A perpetual engine that walks a product's append-only movement ledger in
chronological order and produces period COGS and ending valuation under three
methods:

  - "standard": every unit valued at the product's current standard cost.
  - "average":  moving weighted-average cost, updated on each receipt.
  - "fifo":     first-in-first-out cost layers.

COGS is only accumulated for `sale_out` movements, and (when a window is given)
only for those whose date falls in the window — so date-filtered profit stays
correct even though costing itself is perpetual. Valuation is as-of the latest
movement, or as-of the end of a given local day (`as_of`): the ledger is then
cut at that day and the method runs on what had happened by then.

Stock adjustments (count differences, damage, theft, expiry) are accumulated
apart from COGS as `adjustments`: the cost of what went missing less the cost
of what turned up, valued the way the method values stock leaving (standard:
the movement's cost snapshot; average: the running average; FIFO: the layers
it consumes). Opening stock entered as an adjustment is not a gain and stays
out of that figure (it still builds the cost layers).

Three rules keep the figures honest:

  * Transfers are skipped. A move between two of the company's own warehouses
    is cost-neutral company-wide; letting its two legs through would pop the
    oldest FIFO layer and re-add the stock as a new layer at today's cost.
  * A sales return re-enters at the cost the goods LEFT at (the movement's
    `unit_cost`, stamped by the return), and reverses COGS in the window it
    falls in; inflows without a cost fall back to the standard cost.
  * The weighted average is never computed across a negative balance. An
    oversell (offline sale before the receipt arrives) leaves on-hand below
    zero; the next receipt then sets the average to its own cost instead of
    blending against a phantom negative quantity, which produced averages
    ten times the real price.
"""

from decimal import Decimal

from django.utils import timezone

from inventory.models import StockAdjustment, StockMovement

ZERO = Decimal("0")
STANDARD = "standard"
AVERAGE = "average"
FIFO = "fifo"
METHODS = (STANDARD, AVERAGE, FIFO)

# Movement types that change where stock sits but not what it is worth.
COST_NEUTRAL = {StockMovement.TRANSFER}

# Adjustments that load a business's existing stock rather than record a loss
# or a find: the "opening stock" reason, and the demo/e2e seeders that load
# stock the same way. They are not profit or loss.
OPENING_REFERENCES = ("seed_demo", "seed_e2e")


def is_opening(reference_type, reason_code):
    return (
        reference_type in OPENING_REFERENCES
        or reason_code == StockAdjustment.REASON_OPENING
    )


def _voided_invoices(company_id):
    from sales.models import Invoice

    return {
        str(pk) for pk in
        Invoice.objects.filter(company_id=company_id, is_void=True).values_list("pk", flat=True)
    }


def _stream(product, voided=None, as_of=None):
    """Movements in order. A voided invoice's sale and its reversal still move
    quantities and cost layers, but neither counts toward COGS: revenue drops
    the voided invoice from its own period, and charging its cost there while
    crediting it back in the void's period showed a loss one month and a
    matching gain the next."""
    if voided is None:
        voided = _voided_invoices(product.company_id)
    movements = product.stock_movements.exclude(movement_type__in=COST_NEUTRAL)
    if as_of is not None:
        # The end of that day on the company's calendar (__date is local).
        movements = movements.filter(created_at__date__lte=as_of)
    rows = list(
        movements.order_by("created_at", "id")
        .values("movement_type", "quantity", "unit_cost", "created_at",
                "reference_type", "reference_id", "adjustment__reason_code")
    )
    for row in rows:
        row["voided"] = (
            row["reference_type"] in ("Invoice", "InvoiceVoid")
            and row["reference_id"] in voided
        )
        row["shrinkage"] = (
            row["movement_type"] == StockMovement.ADJUSTMENT
            and not is_opening(row["reference_type"], row["adjustment__reason_code"])
        )
    return rows


def _in_window(when, start, end):
    # The company's calendar day, as revenue uses — a sale at 00:30 in
    # Khartoum is tomorrow's sale, not yesterday's in UTC.
    day = timezone.localtime(when).date()
    if start and day < start:
        return False
    if end and day > end:
        return False
    return True


def _is_sale(m):
    return m["movement_type"] == StockMovement.SALE_OUT


def _is_sales_return(m):
    return m["movement_type"] == StockMovement.SALES_RETURN_IN


def _standard(product, movements, start, end):
    """Standard cost: stock is valued at the product's current standard cost,
    but COGS is what the goods cost when they left. Sale and return
    movements carry that snapshot in unit_cost (returns copy the sale's);
    rows written before the snapshot existed fall back to the current cost.
    Reading the current cost for both made a return during inflation book a
    profit out of thin air (review F12)."""
    fallback = product.cost_price or ZERO
    cogs = ZERO
    adjustments = ZERO
    on_hand = ZERO
    for m in movements:
        qty = m["quantity"]
        on_hand += qty
        if m["voided"] or not _in_window(m["created_at"], start, end):
            continue
        unit = m["unit_cost"] if m["unit_cost"] is not None else fallback
        if _is_sale(m):
            cogs += (-qty) * unit
        elif _is_sales_return(m):
            cogs -= qty * unit
        elif m["shrinkage"]:
            adjustments -= qty * unit
    return {
        "on_hand": on_hand, "cogs": cogs, "adjustments": adjustments,
        "valuation": on_hand * fallback,
    }


def _average(product, movements, start, end):
    fallback = product.cost_price or ZERO
    avg = fallback
    qty_on_hand = ZERO
    cogs = ZERO
    adjustments = ZERO
    for m in movements:
        qty = m["quantity"]
        cost = m["unit_cost"]
        counts = not m["voided"] and _in_window(m["created_at"], start, end)
        if qty > 0:  # inflow updates the moving average
            in_cost = cost if cost is not None else (avg if qty_on_hand > 0 else fallback)
            if qty_on_hand <= 0:
                # Nothing (or less than nothing) to blend with: the receipt
                # defines the new average outright.
                avg = in_cost
            else:
                avg = (qty_on_hand * avg + qty * in_cost) / (qty_on_hand + qty)
            qty_on_hand += qty
            if _is_sales_return(m) and counts:
                cogs -= qty * (cost if cost is not None else avg)
            elif m["shrinkage"] and counts:
                adjustments -= qty * in_cost
        else:  # outflow leaves the average unchanged
            if _is_sale(m) and counts:
                cogs += (-qty) * avg
            elif m["shrinkage"] and counts:
                adjustments += (-qty) * avg
            qty_on_hand += qty
    valuation = qty_on_hand * avg if qty_on_hand > 0 else ZERO
    return {
        "on_hand": qty_on_hand, "cogs": cogs, "adjustments": adjustments,
        "valuation": valuation,
    }


def _fifo(product, movements, start, end):
    fallback = product.cost_price or ZERO
    layers = []  # list of [qty_remaining, unit_cost], oldest first
    oversold = ZERO  # units sold with no layer to draw from
    cogs = ZERO
    adjustments = ZERO
    for m in movements:
        qty = m["quantity"]
        cost = m["unit_cost"]
        counts = not m["voided"] and _in_window(m["created_at"], start, end)
        if qty > 0:
            in_cost = cost if cost is not None else fallback
            # A receipt first settles any earlier oversell before it becomes
            # a layer; those units are already gone.
            settle = min(qty, oversold)
            oversold -= settle
            remainder = qty - settle
            if remainder > 0:
                layers.append([remainder, in_cost])
            if _is_sales_return(m) and counts:
                cogs -= qty * in_cost
            elif m["shrinkage"] and counts:
                adjustments -= qty * in_cost
        else:
            need = -qty
            consumed = ZERO  # cost of the layers this outflow used up
            while need > 0 and layers:
                layer = layers[0]
                take = layer[0] if layer[0] <= need else need
                consumed += take * layer[1]
                layer[0] -= take
                need -= take
                if layer[0] <= 0:
                    layers.pop(0)
            if need > 0:  # consumed past available stock (oversell)
                oversold += need
                consumed += need * fallback
            if _is_sale(m) and counts:
                cogs += consumed
            elif m["shrinkage"] and counts:
                adjustments += consumed
    on_hand = sum((layer[0] for layer in layers), ZERO) - oversold
    valuation = sum((layer[0] * layer[1] for layer in layers), ZERO)
    return {
        "on_hand": on_hand, "cogs": cogs, "adjustments": adjustments,
        "valuation": valuation,
    }


_ENGINES = {STANDARD: _standard, AVERAGE: _average, FIFO: _fifo}


def compute(product, method=STANDARD, start=None, end=None, voided=None, as_of=None):
    """
    Return {on_hand, cogs, adjustments, valuation} for a product under the
    given method. `start`/`end` are dates bounding which sales and stock
    adjustments count; `as_of` cuts the ledger at the end of that local day.
    """
    if method not in _ENGINES:
        method = STANDARD
    return _ENGINES[method](product, _stream(product, voided, as_of), start, end)


def company_totals(company_id, method=STANDARD, start=None, end=None, as_of=None):
    """Aggregate COGS, stock adjustments and valuation across a company's
    products; with `as_of`, the valuation is the stock held at the end of
    that day."""
    from inventory.models import Product

    cogs = ZERO
    adjustments = ZERO
    valuation = ZERO
    per_product = []
    voided = _voided_invoices(company_id)
    for product in Product.objects.filter(company_id=company_id):
        result = compute(product, method, start, end, voided, as_of)
        cogs += result["cogs"]
        adjustments += result["adjustments"]
        valuation += result["valuation"]
        per_product.append((product, result))
    return {
        "cogs": cogs, "adjustments": adjustments, "valuation": valuation,
        "per_product": per_product,
    }
