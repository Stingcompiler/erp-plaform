# Enhancement: Costing-Method Selector on Reports

Status: **built, in review.** Surfaces the FIFO/weighted-average/standard
costing engine (previously API-only) in the Reports UI.

## What was built

- A **Costing method** selector (Standard cost / Weighted average / FIFO) in the
  Reports controls, wired to re-fetch the **inventory valuation** and **profit**
  reports with `?method=` whenever it changes (alongside the existing date
  range).
- The **Profit** card title now reflects the active method (e.g. "Profit
  (FIFO)"), reads the new `cogs` field (falling back to the legacy
  `cogs_standard_cost` alias), and shows the backend's method note ("COGS uses
  fifo costing over the movement ledger.").
- The **Inventory value** KPI and valuation bars now reflect the chosen method,
  since the valuation call passes it through.

`lib/api.js` helpers `inventoryValuation`/`profitSummary` now accept params.

## Verifications actually run here

- All frontend JSX/JS pass a `tsc` syntax check (no TS1xxx/TS17xxx).
- Method values (`standard`/`average`/`fifo`) match the backend's accepted
  `?method=` values; the fetch threads the method into both report calls and the
  `load` dependency list so switching re-queries.

## Deliberately left out

- A **CSV export** honouring the method (the CSV links still use the date range;
  the method could be added to the query string next).
- Persisting the selected method as a **per-user/company default** (it resets to
  Standard on load).

## Known caveat (same as everywhere)

- **Not built/run live here** — `next build`/`next lint` need `npm install`
  (network), so they run in CI. JSX verified with `tsc`.
