# Frontend — Slice 2: Inventory module

Status: **built, in review.**

## What was built

The first real module screen, plus a reusable UI kit that every later module
slice will build on.

**Reusable UI kit (`components/ui/`).** `kit.jsx` (Button with variants, Field,
Input, Select, Badge, Card, PageHeader) and `Drawer.jsx` (slide-over with
backdrop + Esc-to-close, RTL-aware via logical `end-0`). These are the shared
primitives for all future module screens.

**Inventory page (`/inventory`).** A products table (SKU/name/on-hand/reorder/
price in the mono ledger face, with an In-stock/Low status badge), server-side
**search** (SKU/name/barcode), a **low-stock-only** filter, and pagination.
Access is gated: no `inventory` read → an access notice; write actions
(New product, edit, adjust) only render when the role has `inventory` write.

**Product create/edit (`ProductForm`).** A drawer form (SKU, name, category,
cost/sale price, reorder level, batch-tracking) that POSTs/PATCHes
`/api/products/` and surfaces field errors.

**Stock detail (`StockDrawer`).** Opens on row click — shows on-hand and a
by-warehouse breakdown from `/api/products/<id>/stock/`, plus a quick
**adjustment** form (warehouse, ± quantity, reason) that posts to
`/api/stock-adjustments/` and refreshes.

**Backend touch.** Added DRF's built-in `SearchFilter` (no new dependency) to
`ProductViewSet` (`search_fields = sku, name, barcode`) so the search box is
real. Additive and safe — absent `?search=` changes nothing, so existing M2
tests are unaffected.

## Verifications actually run here

- All frontend JSX/JS pass a `tsc` syntax check (no TS1xxx/TS17xxx).
- Backend `inventory/views.py` compiles; `SearchFilter` is used; lint clean;
  repo audit still passes.

## Deliberately deferred (next slices)

- **POS / Sales** checkout screen (the offline-idempotent sale path) — the
  natural next module.
- Category/brand/unit/warehouse management screens (only products + adjustments
  are editable here; the master-data endpoints exist).
- Stock transfers and a full movement history view.
- A shared toast system (currently inline messages) and optimistic updates.

## Known caveat (same as the rest)

- **Not built/run live here** — `next build`/`next lint` need `npm install`
  (network), so they run in CI. JSX verified with `tsc`.

## Next

Module slice 3 — POS / Sales, or another module on request.
