# M9 — Reports & Dashboards

Status: **built, in review.**

## What was built (`reports` app — model-less)

Seven read-only reporting endpoints, all company-scoped and gated to the
`reports` module (M6), with optional `?start=&end=` date filtering. Every figure
is **derived at query time** from the ledgers/documents — there are no stored
report totals:

- `GET /api/reports/sales-summary/` — invoice count, subtotal, tax, total, plus
  a daily series.
- `GET /api/reports/sales-by-product/` — units and revenue per product (top
  sellers); `?format=csv` for export.
- `GET /api/reports/inventory-valuation/` — per product `on_hand × cost_price`
  and a company total (`on_hand` summed from the M2 movement ledger); CSV.
- `GET /api/reports/ar-aging/` — outstanding per customer bucketed
  current/1–30/31–60/61–90/90+, using `Invoice.amount_due()` (so it already
  reflects payments *and* M5 credit notes).
- `GET /api/reports/ap-aging/` — same for supplier bills (reflects M5 debit
  notes).
- `GET /api/reports/purchases-summary/` — bill count, purchases total, receipts.
- `GET /api/reports/profit-summary/` — revenue − COGS (standard cost) = gross
  profit, with an explicit note that COGS uses current standard cost, not FIFO.

## Acceptance criteria

| Criterion | Result |
|---|---|
| Reports return accurate aggregates derived from underlying records | **Covered by tests** — sales summary total = invoice total; sales-by-product units/revenue match the line; valuation = (20−5)×6 = 90; profit = 50 − (5×6) = 20; AR/AP aging totals match `amount_due`. |
| Reports respect company scoping and role visibility | **Covered by tests** — a second company's 999 invoice is excluded; a Landing Page Manager gets 403 on reports. |
| Export available | **Covered by tests** — `?format=csv` returns `text/csv`. |

## Design notes

- **Single source of truth.** Valuation reads `on_hand` from the movement
  ledger; aging reads `amount_due()`, so reports can never disagree with the
  transactional records or with the M5 credit/debit adjustments.
- **RBAC via class attribute.** Report views are class-based `APIView`s with
  `rbac_module = "reports"`, so `RoleModuleAccess` gates them even though there
  is no queryset to infer a module from.

## Deliberately deferred / left out

- **FIFO / weighted-average COGS.** Profit uses current standard cost;
  lot-level costing is a larger costing project.
- **Scheduled / emailed reports and PDF export.** CSV only; the Celery worker
  (`erp-worker`) could generate these later.
- **Cross-company (platform) roll-ups** for Super Administrators — reports are
  single-company.
- **Charting** is left to the frontend; endpoints return the series/data.

## Verifications actually run here

- All backend `.py` compile; lint (fixed 3 long URL lines) + unused-import
  checks clean. `reports` is model-less, so it adds no migration and the
  `makemigrations --check` gate stays green.

## Known caveats (unchanged)

- **Tests not executed live** — no network to install Django; suite written +
  syntax-verified, runs in CI.

## Next

M10 — Backup/Restore, Multi-language, Theme, Security Hardening. Not started
this session. Say "continue".
