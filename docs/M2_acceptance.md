# M2 — Inventory Core

Status: **built, in review.**

## What was built (`inventory` app)

**Master data (company-scoped CRUD):** `Category` (self-nesting), `Brand`,
`Unit`, `Warehouse` (optionally tied to a Branch), and `Product` with SKU
(unique per company), barcode + QR fields, cost/sale price, `reorder_level`,
and a `track_batches` flag. `StockBatch` carries lot number + expiry only.

**The stock ledger — the core of the milestone:**
- `StockMovement` is the single source of truth, with the six required typed
  movements (`purchase_in`, `sale_out`, `adjustment`, `transfer`,
  `sales_return_in`, `purchase_return_out`). `quantity` is **signed**, so
  on-hand for any slice (product / warehouse / batch) is a plain
  `SUM(quantity)`. Sign is validated against the movement type on write.
- **No stored/mutable stock field exists anywhere** — `Product.on_hand()` and
  every endpoint derive quantity from the ledger, satisfying the acceptance
  criterion that levels can never drift. A regression test asserts no
  `quantity`/`quantity_on_hand`/`current_stock` field is ever added.
- `StockAdjustment` generates exactly one `adjustment` movement.
  `StockTransfer` generates exactly two `transfer` movements (−source,
  +dest), so company totals are conserved while per-warehouse totals move.

**Append-only + idempotent (Rules #9 and #2):** movement/adjustment/transfer
endpoints are list/retrieve/create only — no update or delete — so the ledger
is immutable through the API (and the admin). Each accepts a client-generated
`client_uuid`; replaying it returns the existing row (200) instead of
double-applying, which is what makes offline-queued stock actions safe to
re-send. This is the client-idempotency half of Rule #2; the full sync engine
is still M7.

**Endpoints:** `GET /api/products/{id}/stock/` (on-hand + by-warehouse +
by-batch breakdown) and `GET /api/products/low_stock/` (on-hand ≤ reorder
level). All inventory endpoints inherit the M1 company-scoping base, so Rule
#1 isolation and Rule #8 activity logging apply automatically.

## Acceptance criteria

| Criterion | Result |
|---|---|
| Every stock change produces exactly one typed StockMovement row | **Covered by tests** — movement/adjustment = 1 row; transfer = 2 (one per warehouse leg, by design). |
| Stock levels always derivable by summing movements; no separate mutable field | **Covered by tests** — `on_hand` = SUM(quantity); explicit test that no stored-quantity field exists. |

## Verifications actually run here

- All backend `.py` including the inventory migration compile.
- Lint pass clean (no non-migration line >100 chars, no trailing whitespace).
- Index names pinned explicitly in models + migrations so the CI
  `makemigrations --check` gate compares equal deterministically.

## Deliberately deferred / left out

- **Batch picking / FEFO on outbound.** Movements can reference a batch, but
  automatic first-expiry-first-out selection when selling isn't implemented —
  it belongs with Sales (M3) / the costing decision.
- **Inventory valuation / COGS method** (FIFO / weighted average). `unit_cost`
  is captured on movements; no valuation report yet (Reports = M9).
- **Low-stock *notifications*.** There's a low-stock *endpoint*; push/email
  alerts are a Reports/Dashboards (M9) / Celery concern.
- **Barcode/QR *generation*.** Fields exist; image generation is out of scope
  here.
- **Platform-admin-authored inventory.** Inventory endpoints assume a
  company-scoped user (branch staff); a platform admin has no company context
  to attach, and isn't an inventory actor.

## Known caveats (unchanged from M0/M1)

- **Tests not executed live** — no network to install Django here. Suite is
  written (`inventory/tests.py`) and syntax-verified; CI runs it on push.
- **Migrations hand-authored** and gated by `makemigrations --check` in CI.

## Next

M3 — Sales & POS + Manual Payments. Not started this session. Say "continue".
