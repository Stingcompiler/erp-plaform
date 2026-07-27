# Enhancement: Method-Aware CSV Export

Status: **built, in review.** A small completion of the costing-method work.

## What was built

The Reports **inventory-valuation CSV** export now includes the selected
**costing method** in its query string, so a downloaded valuation reflects
Standard / Weighted-average / FIFO exactly as shown on screen. The `csv()`
helper gained an optional extra-params argument; the valuation link passes
`{ method: costMethod }`.

The backend already computes the valuation rows by `method` before building the
CSV, so no server change was needed — the export and the on-screen figures now
match.

## Verifications actually run here

- All frontend JSX/JS pass a `tsc` syntax check (no TS1xxx/TS17xxx).
- Confirmed the valuation report builds its rows from `?method=` before the CSV
  response, so the exported file honours the method.

## Deliberately left out

- Method on the **sales-by-product** CSV (that report is revenue-based, not
  cost-based, so a costing method doesn't apply).

## Known caveat (same as everywhere)

- **Not built/run live here** — `next build`/`next lint` need `npm install`
  (network), so they run in CI. JSX verified with `tsc`.
