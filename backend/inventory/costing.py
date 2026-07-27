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
movement. Inflows without a recorded unit cost (returns, positive adjustments)
fall back to the product's standard cost.
"""

from decimal import Decimal

from inventory.models import StockMovement

ZERO = Decimal("0")
STANDARD = "standard"
AVERAGE = "average"
FIFO = "fifo"
METHODS = (STANDARD, AVERAGE, FIFO)


def _stream(product):
    return list(
        product.stock_movements.order_by("created_at", "id").values(
            "movement_type", "quantity", "unit_cost", "created_at"
        )
    )


def _in_window(when, start, end):
    if start and when.date() < start:
        return False
    if end and when.date() > end:
        return False
    return True


def _standard(product, movements, start, end):
    fallback = product.cost_price or ZERO
    cogs = ZERO
    on_hand = ZERO
    for m in movements:
        qty = m["quantity"]
        on_hand += qty
        if m["movement_type"] == StockMovement.SALE_OUT and _in_window(
            m["created_at"], start, end
        ):
            cogs += (-qty) * fallback
    return {"on_hand": on_hand, "cogs": cogs, "valuation": on_hand * fallback}


def _average(product, movements, start, end):
    fallback = product.cost_price or ZERO
    avg = fallback
    qty_on_hand = ZERO
    cogs = ZERO
    for m in movements:
        qty = m["quantity"]
        cost = m["unit_cost"]
        if qty > 0:  # inflow updates the moving average
            in_cost = cost if cost is not None else (avg if qty_on_hand > 0 else fallback)
            new_qty = qty_on_hand + qty
            if new_qty > 0:
                avg = (qty_on_hand * avg + qty * in_cost) / new_qty
            qty_on_hand = new_qty
        else:  # outflow leaves the average unchanged
            if m["movement_type"] == StockMovement.SALE_OUT and _in_window(
                m["created_at"], start, end
            ):
                cogs += (-qty) * avg
            qty_on_hand += qty
    return {"on_hand": qty_on_hand, "cogs": cogs, "valuation": qty_on_hand * avg}


def _fifo(product, movements, start, end):
    fallback = product.cost_price or ZERO
    layers = []  # list of [qty_remaining, unit_cost], oldest first
    cogs = ZERO
    for m in movements:
        qty = m["quantity"]
        cost = m["unit_cost"]
        if qty > 0:
            layers.append([qty, cost if cost is not None else fallback])
        else:
            need = -qty
            counts = m["movement_type"] == StockMovement.SALE_OUT and _in_window(
                m["created_at"], start, end
            )
            while need > 0 and layers:
                layer = layers[0]
                take = layer[0] if layer[0] <= need else need
                if counts:
                    cogs += take * layer[1]
                layer[0] -= take
                need -= take
                if layer[0] <= 0:
                    layers.pop(0)
            if need > 0:  # consumed past available stock (oversell) — value at fallback
                if counts:
                    cogs += need * fallback
    on_hand = sum((layer[0] for layer in layers), ZERO)
    valuation = sum((layer[0] * layer[1] for layer in layers), ZERO)
    return {"on_hand": on_hand, "cogs": cogs, "valuation": valuation}


_ENGINES = {STANDARD: _standard, AVERAGE: _average, FIFO: _fifo}


def compute(product, method=STANDARD, start=None, end=None):
    """
    Return {on_hand, cogs, valuation} for a product under the given method.
    `start`/`end` are dates bounding which sales count toward COGS.
    """
    if method not in _ENGINES:
        method = STANDARD
    return _ENGINES[method](product, _stream(product), start, end)


def company_totals(company_id, method=STANDARD, start=None, end=None):
    """Aggregate COGS and valuation across a company's products."""
    from inventory.models import Product

    cogs = ZERO
    valuation = ZERO
    per_product = []
    for product in Product.objects.filter(company_id=company_id):
        result = compute(product, method, start, end)
        cogs += result["cogs"]
        valuation += result["valuation"]
        per_product.append((product, result))
    return {"cogs": cogs, "valuation": valuation, "per_product": per_product}
