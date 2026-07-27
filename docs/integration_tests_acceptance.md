# Cross-Milestone Integration Tests

Status: **built, in review.**

## What was built

A suite (`backend/integration/`) that drives whole workflows through the real
HTTP API across several milestones at once — proving the modules cooperate and
the PROJECT_RULES hold end to end, not just per endpoint. Master data is seeded
via the ORM; every workflow step goes through the API. All shapes were read
from the actual serializers/views before writing.

**`test_sell_through.py` — the core lifecycle (M2/M3/M4/M5/M9).**
Receive 100 → on-hand 100 → POS-sell 10 → on-hand 90 → sales-return 4 →
**on-hand still 90** (Rule #5: quarantined, not silently re-shelved) → disposition
*restock* → on-hand 94 → inventory-valuation and sales-summary reports reconcile
with the ledger. A second test proves a *scrap* disposition adds nothing back.

**`test_sync_e2e.py` — offline sync (M7 + M2/M3).**
Push a mixed batch (a stock movement + a POS checkout) → both apply, on-hand
reflects them → replay the same `batch_uuid` → no-op, no duplicate rows → delta
pull returns the company's products. Also: the same op `client_uuid` in a new
batch is deduped.

**`test_isolation_and_rbac.py` — tenancy + roles across workflows (M1/M6).**
Company A can't list, sell into, or receive against company B's records, and
B's data never appears in A's reports or sync pull. A Sales Officer can sell but
gets 403 on receiving; a Purchasing Officer can receive but gets 403 on selling.

**`test_backup_and_tax.py` — backup round-trip (M10) + pluggable tax (M11).**
Back up a populated company → restore the dump into a fresh empty company →
products reappear there; restoring into a non-empty company is refused. And a
real POS invoice renders as `simple` JSON, then as `gulf_vat` XML after the
company's tax format is switched — same invoice, different document (Rule #7).

## Verifications actually run here

- All integration `.py` compile; lint + unused-import checks clean.
- Every `reverse()` name used is confirmed registered in the URL config.
- Response/request shapes cross-checked against `POSCheckoutSerializer`,
  `GoodsReceiptWriteSerializer`, `SalesReturnWriteSerializer` + `disposition`,
  the reports endpoints, sync push/pull, `ops` backup/restore, and the tax
  document endpoint.

## Known caveat (same as everywhere)

- **Not executed live here** — no network to install Django, so the suite runs
  in CI (`pytest -v` collects `integration/` automatically). These tests are the
  main thing that moves the project from "written and verified" toward "proven
  working" once CI runs green.

## What remains (genuinely optional polish)

- Deferred backend items: durable off-site backup storage, FIFO/weighted-average
  COGS, bank-transfer supplier payments, real e-invoicing compliance,
  branch-level row visibility.
- Frontend polish: shared toast system, website sections editor, offline-queue
  UI, password reset.
