# Frontend — Slice 4: Reports module

Status: **built, in review.**

## What was built

The analytics screen over the M9 reporting endpoints — read-only, and rendered
with dependency-free CSS bars (no charting library added, so nothing new to risk
an unverifiable build).

**Reports page (`/reports`).** A date-range filter (From/To/All-time) that
drives the period-sensitive reports, plus:
- **Headline KPIs**: invoices, revenue, gross profit, inventory value.
- **Top products by revenue** and **inventory value by product** as horizontal
  bar lists (`BarList` — divs sized by share of max), each with a **CSV export**
  link straight to the `?format=csv` endpoint (a top-level GET navigation, so
  the SameSite=Lax auth cookie is sent).
- **Profit (standard cost)**: revenue / COGS / gross profit, with the "standard
  cost, not FIFO" note surfaced from the API.
- **AR aging** table bucketed current / 1–30 / 31–60 / 61–90 / 90+, with the
  oldest bucket flagged.

Access is gated to the `reports` module; every figure comes straight from the
ledger-derived M9 endpoints.

## Verifications actually run here

- All frontend JSX/JS pass a `tsc` syntax check (no TS1xxx/TS17xxx).
- Report response shapes match the M9 endpoints authored earlier
  (`sales-summary.totals/daily`, `inventory-valuation.total_value/items`,
  `ar-aging` buckets, `profit-summary`), so this slice consumes known shapes.

## Deliberately deferred (next slices)

- **Purchasing, Returns, Users, Website, Settings** screens (APIs live;
  placeholders remain).
- Richer charts (time-series line, trends) — the current bars are intentionally
  dependency-free.
- Drill-down from a report figure into the underlying records.

## Known caveat (same as the rest)

- **Not built/run live here** — `next build`/`next lint` need `npm install`
  (network), so they run in CI. JSX verified with `tsc`.

## Next

Purchasing (suppliers, receiving, bills) is the natural next module, or wire a
deferred backend item — say which.
