# PROJECT_RULES.md — Read this in full before doing any work this session

You are building a commercial, multi-company ERP platform. This file is the fixed constitution for the project. It does not change between sessions. If anything you're about to do conflicts with a rule below, stop and flag the conflict instead of proceeding.

## Tech stack — do not substitute or "improve upon" without being asked

- Frontend: Next.js (App Router), JavaScript, Tailwind CSS, Framer Motion, Lucide React, Axios, Context API
- Backend: Django 5, Django REST Framework, JWT auth via HttpOnly cookies, PostgreSQL (prod) / SQLite (dev)
- Background jobs: Celery
- Backend is one Django monolith. Do not split it into microservices or separate deployable backend services.

## Deployment — Render, native runtimes, no containers

- Do not create a Dockerfile, docker-compose.yml, or any containerization config, ever, even if it seems like good practice. This is a hard rule, not a default you can override for convenience.
- One web service, deployed the traditional way (Render builds directly from the Git repo, no Docker):
  - `erp-api` — Python native runtime, Django + DRF via Gunicorn. Its build step also builds the Next.js frontend as a static export and Django serves it directly (`backend/core/frontend.py`) — no separate frontend service, no cross-service CORS in production. Locally, `next dev` on `:3000` against this API on `:8000` over CORS is still the dev workflow (fast refresh); the static-export serving path only activates when `DEBUG=False`.
- `erp-worker` — Render Background Worker (Python native), runs Celery
- `erp-backup-cron` — Render Cron Job (Python native), scheduled backups
- `erp-db` — Render managed PostgreSQL
- `erp-cache` — Render managed Key Value (Redis-compatible), used as the Celery broker
- All five services should be defined in a single `render.yaml` Blueprint at the repo root, kept in sync as services are added.

## Hosting model

This is hosted centrally on Render by the platform owner. Businesses are tenants inside one deployment, isolated logically by `company_id` — this is not a "customer downloads and self-hosts" product.

## Non-negotiable architecture rules

1. **Every query is scoped by `company_id`.** No endpoint may return cross-company data under any circumstance, including by a user guessing another company's object ID. Enforce this with shared middleware or a base queryset mixin used by every viewset — not ad hoc checks added per-view, which get missed.
2. **Offline-first is the default assumption**, not an add-on. Any create/update endpoint used by branch-level staff (sales, stock movements, payments) must be safely queueable client-side and idempotent server-side — replaying the same action twice must not double-apply it.
3. **Payments are manually recorded only. Never integrate a payment gateway.** A `Payment` record stores: method (`cash` / `bank_transfer`), the company's receiving bank account (`CompanyBankAccount`), the sender's bank name, the last 4 digits of the transaction reference, amount, who recorded it, and a timestamp. No external API calls of any kind for payments. Include a `verified_at` / `verified_by` pair for later manual reconciliation by a manager — this never blocks the sale from completing.
4. **Returns are always child records of the original document, never standalone.** A `SalesReturn` line must reference an `InvoiceLine`; a `PurchaseReturn` line must reference a `ReceivingLine`. Enforce, at the database or serializer level, that quantity returned can never exceed the original line's quantity.
5. **Returned stock never automatically re-enters sellable inventory.** Every return requires an explicit disposition: `sellable`, `damaged_quarantine`, or `written_off`.
6. **Every return generates a formal Credit Note (sales) or Debit Note (purchase)** — a distinct, sequentially-numbered document type. Model this fully now, even though today it's just printed/logged — a future jurisdiction config will need these to carry additional compliance fields without a schema rewrite.
7. **Tax and invoice behavior is jurisdiction-pluggable from day one.** Every company has a `TaxProfile` (`country`, `invoice_format`, `e_invoicing_enabled`), even though today only a simple flat-rate, plain-invoice profile is implemented. Never hardcode country-specific assumptions directly into the `Invoice` model.
8. **Every state-changing action writes to the Activity Log**, not just the ones that feel important: login, logout, create/update/delete on Product, Invoice, Payment, Return, User, permission changes, backups, restores, landing page edits.
9. **Financial and audit records are append-only.** Payments, Invoices, Returns, and Stock Movements are never edited in place. A correction is always a new offsetting entry, so history is never erased.

## Core data model shape (extend this, don't restructure it once M1–M2 land)

- Identity/Org: `User`, `Role`, `Permission`, `Company`, `Branch`, `Department`
- Inventory: `Product`, `Category`, `Brand`, `Unit`, `Warehouse`, `StockBatch` (with `expiry_date`, `lot_number`), `StockMovement` (typed: `sale_out`, `purchase_in`, `adjustment`, `transfer`, `sales_return_in`, `purchase_return_out`)
- Sales: `Customer`, `Quotation`, `SalesOrder`, `Invoice`, `InvoiceLine`, `Payment`, `CompanyBankAccount`
- Purchasing: `Supplier`, `PurchaseOrder`, `Receiving`, `ReceivingLine`
- Returns: `SalesReturn`, `SalesReturnLine`, `PurchaseReturn`, `PurchaseReturnLine`, `CreditNote`, `DebitNote`
- CRM: `CustomerGroup`, `Lead`, `FollowUp`, `Note`
- HR: `Employee`, `Position`, `Attendance`, `LeaveRequest`, `PerformanceRecord`, `EmployeeDocument`
- Platform: `ActivityLog`, `SyncQueueItem`, `SyncLog`, `BackupRecord`, `TaxProfile`

## Explicitly out of scope — do not add any of these unless directly instructed

- Payment gateway integrations of any kind
- Live ZATCA/UAE Peppol e-invoicing integration (only the `TaxProfile` stub interface, once you reach that milestone)
- Full general ledger / double-entry accounting (track AR/AP balances at the document level only)
- Manufacturing, BOM, or work orders
- Multi-currency accounting beyond a currency field + exchange-rate snapshot per transaction
- Docker or any containerization

## How you must work

- Commit in small, reviewable units per feature, not one giant commit per milestone.
- Write tests alongside the code you write, not after. A milestone is not done until its stated acceptance criteria pass with visible test output.
- If completing your current task would require changing a data model from an earlier milestone, stop and report that instead of changing it silently.
- At the end of every session: report (1) what you built, (2) what you deliberately deferred or left out, (3) test results. Do not start the next milestone in the same session unless told to.
