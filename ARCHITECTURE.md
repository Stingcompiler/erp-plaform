# Architecture & Project Reference

This document is the single consolidated overview of the ERP platform — the map
that ties together the per-milestone and per-enhancement notes in `docs/`. Read
`README.md` first for quickstart and local dev; read `DEPLOYMENT.md` for the
Render runbook; read `PROJECT_RULES.md` for the binding constraints. This file
explains how the pieces fit and where to look.

## 1. What this is

A commercial, multi-company ERP for small and mid-sized businesses (built with
Sudan and the Gulf in mind: English/Arabic, RTL, manual bank-transfer payments).
It is a Django 5 + DRF monolith that also serves the Next.js (App Router)
frontend as a static export — one deployable service — on Render with native
runtimes only — **no Docker anywhere** in the repo, per PROJECT_RULES. Locally,
the frontend still runs via `next dev` against the API over CORS for fast
refresh; see `backend/core/frontend.py` for the production serving path.

At a glance:

| Layer | Stack | Location |
|---|---|---|
| Backend | Django 5, DRF, cookie-JWT, Postgres | `backend/` |
| Frontend | Next.js App Router (static export), Tailwind, axios | `frontend/` |
| Deploy | Render Blueprint (5 native components, frontend built into `erp-api`) | `render.yaml`, `DEPLOYMENT.md` |
| CI | GitHub Actions (audit → lint → checks → tests → build) | `.github/workflows/ci.yml` |

## 2. The nine PROJECT_RULES and where they live

Every rule is enforced in code, not just documented:

1. **Company data isolation** — `core/scoping.py`
   (`CompanyScopedQuerySetMixin`): every company-owned viewset filters by the
   user's company and forces `company` on create; cross-company ids 404.
2. **Offline-first / idempotent writes** — `client_uuid` on POS checkout,
   receiving, returns, sync ops; `IdempotentCreateMixin` and the M7 sync
   registry dedupe replays.
3. **Manual payments only, never a gateway** — `Payment` / `SupplierPayment`
   record cash or bank transfer with a reference; no gateway integration exists.
4. **Auth via cookie-JWT** — `accounts/` (custom email-login user, rotating +
   blacklistable refresh tokens, `HttpOnly` cookies).
5. **Returned stock never silently re-shelved** — `returns/` quarantine →
   explicit disposition (restock/scrap); only restock posts a
   `sales_return_in` movement.
6. **Role-based visibility** — `core/rbac.py` (`ROLE_MODULE_MATRIX`,
   `RoleModuleAccess`); plus opt-in **row-level branch** scoping in
   `core/scoping.py`.
7. **Pluggable tax / invoice format** — `tax/handlers.py` (Simple + Gulf VAT
   scaffold), switchable per company via `TaxProfile`.
8. **ActivityLog audit** — `core/activity.py` + `ActivityLoggingMixin`; login,
   logout, and CRUD are logged.
9. **Financial records append-only** — `AppendOnlyScopedViewSet`; the stock
   ledger and invoices have no destructive update/delete path. Corrections
   are offsetting documents: `POST /invoices/{id}/void/` writes a full credit
   note, reverses the sale's stock movements at their original cost and, when
   anything was paid, a `Refund`; credit/debit notes and supplier bills have
   a manager-only `void` action that flags the row and leaves it in place;
   `Refund` (`/api/refunds/`) is the only way money goes back to a customer,
   capped at the credit note and written to the drawer as a linked movement.

## 3. Backend architecture

Fourteen Django apps under `backend/`, each company-scoped:

- **core** — shared scoping/RBAC bases, activity log, dashboard, health,
  scheduled-backup command, `scripts/repo_audit.py`.
- **accounts** — custom `User` (email login, branch/role FKs), `Role`
  (platform/business/branch scope), cookie-JWT, seed_roles, password policy.
- **org** — `Company` (auto-creates a `TaxProfile`), `Branch`, `Department`.
- **inventory** — catalog + the **`StockMovement` ledger** (signed quantities,
  append-only; on-hand is `SUM(quantity)`), warehouses, adjustments, transfers,
  and the perpetual **costing engine** (`costing.py`).
- **sales** — customers, gapless `InvoiceSequence`, quotations, sales orders,
  invoices + lines, payments, company bank accounts, and **POS checkout**
  (`/api/pos/checkout/`).
- **purchasing** — suppliers, purchase orders, **goods receipts**
  (`/api/receivings/`), bills, supplier payments.
- **returns** — sales/purchase returns, the **quarantine → disposition** flow
  (Rule #5), credit/debit notes.
- **crm** — `CustomerGroup`, `Lead` (6-stage pipeline), `FollowUp`, `Note`;
  `/api/leads/pipeline/` summary drives the CRM board (M6).
- **hr** — `Position`, `Employee`, `Attendance` (unique per employee/day),
  `LeaveRequest` (approve/reject actions), `PerformanceRecord`,
  `EmployeeDocument` (M6).
- **sync** — the M7 offline batch protocol (`/api/sync/push|pull/`), op- and
  batch-level idempotency, an op registry reusing the domain serializers.
- **website** — singleton `Website`, `Section`s, `FeaturedProduct`s, publish
  toggle, and an unauthenticated public site by slug.
- **reports** — model-less live reports (sales, inventory valuation, AR/AP
  aging, profit), CSV export, and costing-method selection.
- **tax** — the pluggable handler registry + the invoice document endpoint.
- **ops** — backups (with optional **durable S3/R2 storage**), restore,
  user preferences (language/theme), and languages.

### Cross-cutting patterns

- **The ledger is the source of truth.** Stock is never a stored integer; it's
  the sum of append-only `StockMovement` rows. Reports and costing read the same
  ledger, so figures can't drift from reality.
- **Idempotency everywhere writes happen.** Client-generated UUIDs make POS
  sales, receipts, returns, and synced operations safe to retry — essential for
  the offline-first requirement.
- **Scoping is inherited, not repeated.** Viewsets inherit
  `CompanyScopedModelViewSet` / `AppendOnlyScopedViewSet`; company isolation and
  (opt-in) branch filtering are applied once, centrally.

## 4. Frontend architecture

Next.js App Router under `frontend/`:

- **Providers** wrap the authenticated app in `app/(app)/layout.jsx`:
  `AuthProvider` (session + RBAC access map + preferences),
  `ToastProvider` (app-wide feedback), and `SyncProvider` (online status +
  offline queue drain).
- **`AppShell`** renders an RBAC-filtered left rail (driven by the access map,
  so users only see modules they can read) with a mobile hamburger drawer, and a
  topbar with language, theme, sync status, and sign-out.
- **Twelve module screens**: Dashboard, Inventory, Sales (POS + invoices +
  bank accounts), Purchasing, Returns, CRM (pipeline + leads + follow-ups),
  HR (employees + leave), Reports, Website, Organization, Users, Settings.
- **Public marketing landing page** at `/` for logged-out visitors
  (`components/landing/`), separate from the authenticated app.
- **Design system**: slate-navy + teal on cool paper, RGB-channel CSS tokens
  for opacity, full dark mode, and full **bilingual EN/AR with RTL** — a
  localStorage/cookie-persisted `I18nProvider` swaps Inter/Sora (LTR) for
  Cairo/Tajawal (RTL) by direction.
- **Offline-first UX**: `lib/syncQueue.js` (localStorage) + `SyncProvider`
  buffer POS sales when offline and drain them through the sync endpoint when
  connectivity returns.

## 5. The costing engine

`inventory/costing.py` walks the movement ledger chronologically and produces
period COGS and ending valuation under three methods — **standard**,
**weighted-average**, **FIFO** — with date-window attribution so filtered profit
stays correct. Reports default to `standard` (preserving prior behavior) and
accept `?method=`. See `docs/enhancement_costing_acceptance.md`.

## 6. Testing & the honest verification caveat

- **Unit tests** live per app (`tests.py` / `test_*.py`); **cross-milestone
  integration tests** live in `backend/integration/` and drive whole workflows
  (sell-through, offline sync, tenancy/RBAC, backup+tax) through the real API.
- **CI** (`.github/workflows/ci.yml`) runs: repo audit → flake8 →
  `manage.py check` → `makemigrations --check` → `check --deploy`
  (informational) → `pytest`, then the frontend lint + build.
- **Important, stated on every acceptance doc:** the build sandbox had **no
  network and no Django/npm install**, so nothing was executed live there.
  Everything was verified offline — `py_compile` on all Python, hand-authored
  migrations, a manual lint pass, YAML validation, the repo audit, and `tsc`
  syntax checks on the frontend. The full test suite and `next build` run in
  **CI on first push**. That first CI run is the thing to watch on deploy.

## 7. Enhancements beyond the plan

The original M0–M12 plan, the frontend, and the integration suite are complete.
Thirteen enhancements were added on top, each with an acceptance doc:

| Enhancement | Doc |
|---|---|
| FIFO / weighted-average costing | `enhancement_costing_acceptance.md` |
| Bank-transfer payments (POS + supplier) | `enhancement_bank_transfer_acceptance.md` |
| Durable off-site backup storage (S3/R2) | `enhancement_backup_storage_acceptance.md` |
| Restore from object storage | `enhancement_restore_from_storage_acceptance.md` |
| Branch-level row visibility | `enhancement_branch_visibility_acceptance.md` |
| Reports costing-method selector | `enhancement_reports_costing_selector_acceptance.md` |
| User branch selector | `enhancement_user_branch_selector_acceptance.md` |
| Website sections editor | `enhancement_website_sections_acceptance.md` |
| Shared toast system | `enhancement_toast_system_acceptance.md` |
| Offline queue UI | `enhancement_offline_queue_acceptance.md` |
| Admin password reset | `enhancement_password_reset_acceptance.md` |
| Branch management screen | `enhancement_branch_management_acceptance.md` |
| Method-aware CSV export | `enhancement_method_aware_csv_acceptance.md` |
| Featured products management | `enhancement_featured_products_acceptance.md` |

## 8. Reading guide to `docs/`

- **The plan**: `erp_ai_agent_build_plan.md`.
- **Backend milestones**: `M0`–`M12_acceptance.md` (M0 scaffold → M12
  deploy/hardening). Each lists what was built, acceptance criteria, and the
  verification caveat.
- **Frontend slices**: `frontend_slice1`…`slice7_admin` (foundation → inventory
  → sales → reports → purchasing → returns → admin).
- **Integration**: `integration_tests_acceptance.md`.
- **Enhancements**: the 13 `enhancement_*` docs (table above).

## 9. Known limitations / future work

Deliberately out of scope, noted in the relevant docs: real e-invoicing
compliance (ZATCA signing/QR — the Gulf handler is a scaffold); self-service
password reset by email (needs an SMTP/provider backend); per-warehouse cost
layers and landed-cost allocation; movement/report scoping via
`warehouse__branch` joins; drag-and-drop reordering for website sections and
featured products; and department management. None are required by the plan.
