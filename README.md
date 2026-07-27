# ERP Platform

Multi-company ERP platform. Django 5 + DRF monolith backend, Next.js
(App Router) frontend, deployed on Render with native runtimes only — no
Docker anywhere in this repo (see `PROJECT_RULES.md`).

> For a full system overview — architecture, how every PROJECT_RULE is
> enforced, the enhancement catalog, testing methodology, and a guide to all
> the `docs/` acceptance notes — see **`ARCHITECTURE.md`**.

This repo is being built milestone-by-milestone per
`docs/erp_ai_agent_build_plan.md`. **`PROJECT_RULES.md` is the fixed
constitution for the project — read it in full before touching any code.**

## Repo structure

```
/backend        Django project (config/), apps per domain as milestones land
/frontend       Next.js app (App Router)
render.yaml     Render Blueprint — all 6 services as infra-as-code
docs/           Per-milestone acceptance notes
PROJECT_RULES.md
```

## Local development

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver
# → http://localhost:8000/api/health/
```

### Frontend

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
# → http://localhost:3000
```

With both running, the home page at `localhost:3000` pings
`/api/health/` and shows whether the backend is reachable.

### Background worker (optional locally)

Requires a locally running Redis (not via Docker — install natively, e.g.
`apt install redis-server` / `brew install redis`):

```bash
cd backend
celery -A config worker --loglevel=info
```

## Deployment

`render.yaml` at the repo root defines all 6 services (`erp-api`,
`erp-frontend`, `erp-worker`, `erp-backup-cron`, `erp-db`, `erp-cache`).
Connect the repo as a Render Blueprint; Render builds and runs each
service natively from source — no Dockerfile involved at any point.

## Milestone status

See `docs/` for per-milestone build notes.

- **M0 — Scaffolding & Environment** — built.
- **M1 — Auth, Users, Roles, Company/Branch/Department** — built.
- **M2 — Inventory Core** — built.
- **M3 — Sales & POS + Manual Payments** — built.
- **M4 — Purchasing & Suppliers** — built.
- **M5 — Returns & Credit Notes** — built.
- **M6 — Role-Based Visibility & Dashboards** — built.
- **M7 — Offline Sync Engine** — built.
- **M8 — Public Website / Landing Page Generator** — built.
- **M9 — Reports & Dashboards** — built.
- **M10 — Backup/Restore, Multi-language, Theme, Security Hardening** — built.
- **M11 — Pluggable Tax / E-invoicing Scaffold** — built.
- **M12 — Deployment Hardening & Blueprint Verification** — built, in review.

**All milestones (M0–M12) are complete.** See `DEPLOYMENT.md` for the deploy
runbook and `docs/M*_acceptance.md` for per-milestone detail.

### Pluggable tax / invoicing (M11)

```
GET/PATCH /api/tax/profile/     # country, invoice_format, flat_tax_rate, e-invoicing
GET  /api/tax/handlers/         # available jurisdiction handlers
GET  /api/invoices/<id>/document/   # renders via the company's handler (JSON or XML)
```

Switching a company's `invoice_format` (e.g. `simple` -> `gulf_vat`) changes tax
computation and invoice rendering with no change to the Invoice model (Rule #7).

### Ops, preferences, security (M10)

```
POST/GET /api/ops/backups/          # create/list backups (settings role)
POST     /api/ops/backups/restore/  # guarded restore into an empty company
GET/PATCH /api/ops/preferences/     # language (en/ar -> ltr/rtl) + theme
GET      /api/ops/languages/
```

Password policy (min 10, validators), refresh-token rotation, login throttling,
and production security headers (HSTS, SSL redirect, secure cookies) are on.
The `erp-backup-cron` job now performs real per-company backups.

### Reports (M9)

```
GET /api/reports/sales-summary/     ?start=&end=
GET /api/reports/sales-by-product/  ?format=csv
GET /api/reports/inventory-valuation/   (on_hand x cost, from the ledger)
GET /api/reports/ar-aging/   /api/reports/ap-aging/
GET /api/reports/purchases-summary/     /api/reports/profit-summary/
```

All read-only, company-scoped, gated to the reports role, derived from the
underlying ledgers/documents (no stored totals).

### Public website (M8)

```
GET/PATCH /api/website/page/          # auto-generated, editable (website role)
POST /api/website/page/publish/
/api/website/sections/  /api/website/featured-products/
GET /api/public/site/<slug>/          # UNAUTHENTICATED; published content only
```

Public endpoint serves only published, visible, public-safe fields by company
slug; editing is gated to the Landing Page Manager role.

### Offline sync (M7)

```
POST /api/sync/push/    # drain offline queue; per-op idempotent + isolated
GET  /api/sync/pull/?since=<iso>   # delta of changes for readable modules
```

Every write path's `client_uuid` feeds op-level idempotency; `batch_uuid` gives
whole-batch idempotency. Synced ops reuse the same serializers as the live
endpoints, so all business rules apply identically.

### RBAC & dashboards (M6)

```
GET /api/rbac/access/   # {module: level} map for the current user's role
GET /api/dashboard/     # role-scoped summary (only permitted sections)
```

All M1–M5 endpoints are now role-gated (403 when a role lacks module access);
the 11 seeded roles map to per-module read/write/none access in `core/rbac.py`.

### Returns endpoints (M5)

```
POST /api/sales-returns/                 # creates return; stock stays quarantined
POST /api/sales-returns/{id}/disposition/  # restock (-> sales_return_in) or scrap
POST /api/purchase-returns/              # posts purchase_return_out immediately
/api/credit-notes/   /api/debit-notes/   # reduce AR / AP (append-only)
```

Rule #5: returned stock never silently re-enters sellable inventory — it stays
quarantined until a deliberate disposition.

### Purchasing endpoints (M4)

```
/api/suppliers/            (derived ap_balance)
/api/purchase-orders/      (+/{id}/set_status/)
POST /api/receivings/      # atomic, idempotent goods receipt -> purchase_in stock
/api/goods-receipts/       (read-only)
/api/bills/                (payables, status derived)
/api/supplier-payments/    (+/{id}/verify/, manual only)
```

### Key API endpoints (through M3)

```
# Auth (M1)
POST /api/auth/login/  logout/  refresh/    GET /api/auth/me/
# Org (M1)
/api/companies/  /api/branches/  /api/departments/  /api/users/
# Inventory (M2)
/api/products/ (+/{id}/stock/, /low_stock/)  /api/warehouses/  /api/categories/ ...
/api/stock-movements/  /api/stock-adjustments/  /api/stock-transfers/
# Sales (M3)
/api/customers/  /api/bank-accounts/  /api/quotations/  /api/sales-orders/
/api/invoices/ (read-only)   /api/payments/ (+/{id}/verify/)
POST /api/pos/checkout/       # offline-capable, idempotent sale completion
```

Payments are manual only (cash / bank transfer) — no payment gateway, ever
(Rule #3). Invoices/payments/stock movements are append-only (Rule #9);
invoice numbers are gapless per company.
