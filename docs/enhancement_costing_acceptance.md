# Enhancement: Inventory Costing (FIFO + Weighted-Average COGS)

Status: **built, in review.** Beyond the original plan — closes the standard-cost
limitation flagged in M9.

## What was built

A perpetual costing engine (`inventory/costing.py`) that walks a product's
append-only movement ledger chronologically and produces period COGS and ending
valuation under three methods:

- **standard** — every unit at the product's current standard cost (the prior,
  default behavior).
- **average** — moving weighted-average cost, updated on each receipt.
- **fifo** — first-in-first-out cost layers.

COGS accumulates only for `sale_out` movements, and — when a date window is
given — only for sales inside it, so date-filtered profit stays correct even
though costing is perpetual. Valuation is as-of the latest movement. Inflows
without a recorded unit cost (returns, positive adjustments) fall back to the
product's standard cost. Overselling past available stock is valued at the
fallback cost rather than crashing.

**Wired into the reports (M9):**
- `GET /api/reports/inventory-valuation/?method=fifo|average|standard`
- `GET /api/reports/profit-summary/?method=fifo|average|standard`

Both **default to `standard`**, so existing behavior and the M9 tests are
unchanged. The profit response keeps the `cogs_standard_cost` alias for
backward compatibility alongside the new `cogs`/`method` fields.

## Acceptance criteria

| Criterion | Result |
|---|---|
| FIFO COGS/valuation are correct | **Covered** — receipts 10@5 then 10@8, sell 15 → FIFO COGS 90, valuation 40. |
| Weighted-average is correct | **Covered** — avg 6.5 → COGS 97.5, valuation 32.5. |
| Standard unchanged | **Covered** — COGS 105, valuation 35; report default is `standard`. |
| Date window bounds COGS | **Covered** — a future `start` yields zero COGS but unchanged valuation. |
| Reports honour `?method=` | **Covered** — `CostingReportTests` checks both endpoints. |

## Verifications actually run here

- All backend `.py` compile; lint + unused-import checks clean; repo audit
  passes. **No model change** → no migration; the `makemigrations --check` gate
  stays green. Default path is byte-for-byte the old standard computation, so
  M9's tests still hold.

## Deliberately left out

- **Per-warehouse cost layers** (costing is per product across warehouses).
- **Landed-cost allocation** (freight/duty spread across receipt lines).
- A **method setting** persisted on the company (method is per-request for now;
  a stored default could be added to `TaxProfile`/a costing profile later).
- Frontend method selector on the Reports screen (API-only for now).

## Known caveat (same as everywhere)

- **Not executed live here** — no network to install Django; tests run in CI.
