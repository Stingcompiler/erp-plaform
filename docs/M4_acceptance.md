# M4 — Purchasing & Suppliers

Status: **built, in review.**

## What was built (`purchasing` app)

**Master data:** `Supplier` with derived `ap_balance` (document-level, never
stored).

**Purchase orders:** `PurchaseOrder` + `PurchaseOrderLine` (create/list/
retrieve + `set_status`), totals computed from lines with tax from the
company's `TaxProfile` (Rule #7).

**Goods receipt — the core flow:** `GoodsReceipt` + `GoodsReceiptLine` created
via `POST /api/receivings/`, one atomic, idempotent call. Each line posts
exactly one `purchase_in` StockMovement (reusing the M2 ledger), so on-hand
rises by exactly the received quantity. When a product is batch-tracked and a
lot number is supplied, a `StockBatch` is created/linked and the movement
references it. Receiving is append-only and replay-safe via `client_uuid`
(Rule #2).

**Payables:** `Bill` (the supplier's invoice to us) carries the supplier's
external invoice number, with status derived from payments
(`open`/`partially_paid`/`paid`). `SupplierPayment` records money **we** pay
out — manual only (Rule #3 spirit), no gateway or external calls; bank
transfers record which company account it was paid from plus the last-4
reference. Both are append-only; supplier payments support the same
`verify` reconciliation step as customer payments.

All endpoints inherit the M1 company-scoping + activity-logging base.

## Acceptance criteria

| Criterion | Result |
|---|---|
| Receiving goods increases stock by exactly the received quantity (purchase_in) | **Covered by tests** — `ReceivingTests`: one `purchase_in` movement of the exact qty; `on_hand` rises to match; batch-tracked receiving creates the batch and derives batch on-hand. |
| Supplier AP is derivable at the document level | **Covered by tests** — `APBalanceTests`: bill 500 − payment 200 → `ap_balance` 300; bill status derived. |
| Purchasing is company-scoped, offline/idempotent where relevant | **Covered by tests** — receiving idempotent replay; cross-company product receive rejected; supplier list scoped; payments append-only. |

## Verifications actually run here

- All backend `.py` incl. the 7-model purchasing migration compile.
- Lint clean (fixed one 101-char line); unused-import check clean.

## Deliberately deferred / left out

- **PO ↔ receipt reconciliation** (partial receipts advancing PO status
  automatically, over-receipt warnings). `set_status` is manual for now.
- **Three-way match** (PO ↔ receipt ↔ bill) enforcement — bills can reference a
  PO/receipt but matching isn't enforced.
- **Purchase returns** — `purchase_return_out` movement type exists (M2) but
  the returns flow is M5.
- **Landed cost / valuation** beyond capturing `unit_cost` on movements
  (valuation is M9).

## Known caveats (unchanged)

- **Tests not executed live** — no network to install Django; suite written +
  syntax-verified, runs in CI.
- **Migrations hand-authored**, gated by `makemigrations --check` in CI.

## Next

M5 — Returns & Credit Notes. Not started this session. Say "continue".
