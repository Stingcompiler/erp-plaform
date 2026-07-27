# ERP Platform — AI Coding Agent Execution Plan

**Purpose of this document:** This is not the architecture blueprint — it's the *execution plan* derived from it, written so an AI coding agent (e.g. Claude Code) can build this system phase by phase without re-litigating decisions or drifting in scope. Feed the agent **one milestone at a time**, not the whole document at once. Each milestone is sized to be reviewable as a unit of work — attempting several milestones in a single agent session will blow the context budget and produce unreviewable diffs.

---

## 0. How to use this document with an agent

1. Create a `PROJECT_RULES.md` in the repo root containing Section 2 (Non-Negotiable Architecture Rules) verbatim. Instruct the agent to re-read it at the start of every session. This is what keeps 13 separate milestones — likely run across many separate sessions/days — internally consistent.
2. Paste **one milestone section** (Section 5) into the agent per session. Do not paste ahead.
3. After each milestone, require the agent to: (a) list what it built, (b) list what it explicitly deferred, (c) run and show test results, before you approve moving to the next milestone.
4. Never let the agent silently make a decision flagged as "⚠️ DECISION NEEDED" below — those must be answered by you first.
5. Treat schema/model changes as high-risk: once M1–M2 establish the core data model, later milestones should extend it, not restructure it. If an agent proposes altering a core table's shape, that's a checkpoint to stop and review, not approve in-line.

---

## 1. Tech Stack (pin these exactly, don't let the agent substitute)

**Frontend:** Next.js (App Router), JavaScript, Tailwind CSS, Framer Motion, Lucide React, Axios, Context API
**Backend:** Django 5 (single monolith — no microservices), Django REST Framework, JWT via HttpOnly cookies, PostgreSQL (prod), SQLite (dev)
**Supporting infra:** Celery (background jobs, scheduled backups, sync processing)
**Deployment target:** Render, native runtimes only — **no Docker, no containers**. Two Render services, each deployed the traditional way (connect the Git repo, Render builds and runs it natively per language):

| Render service | Type | Runtime | Purpose |
|---|---|---|---|
| `erp-api` | Web Service | Python (native, no Docker) | Django + DRF, served via Gunicorn |
| `erp-frontend` | Web Service | Node (native, no Docker) | Next.js, served via `next start` |
| `erp-worker` | Background Worker | Python (native) | Celery worker (sync processing, report generation) |
| `erp-backup-cron` | Cron Job | Python (native) | Scheduled backup job |
| `erp-db` | Managed PostgreSQL | — | Render-managed, not self-run |
| `erp-cache` | Managed Key Value (Redis-compatible) | — | Celery broker + result backend |

This keeps the **backend itself as one Django monolith** (single codebase, single set of migrations, no service-to-service network calls between "modules") while still running as two deployed processes on Render, which is unavoidable since Django and Next.js are different language runtimes — Render can't run both under one native service without Docker. "Monolithic" here means: **no microservice decomposition of the backend**, not "literally one process."

**Repo structure:**
```
/erp-platform
  /backend        (Django project, apps per domain: core, inventory, sales, purchasing, crm, hr, returns, reports, website)
  /frontend        (Next.js app)
  render.yaml       (Render Blueprint — defines all services above as infra-as-code, optional but recommended over manual dashboard setup)
  PROJECT_RULES.md
  /docs             (per-milestone acceptance notes)
```

⚠️ **DECISION NEEDED before M0 — flagging an implication of choosing Render:** deploying on Render means **you (the platform owner) host this centrally** — it's not a "customer downloads and runs it on their own server" self-hosted product anymore, since Render is your infrastructure, not theirs. That's a different distribution model than "purchase, deploy, and own independently" implied earlier. This plan now assumes: **you host one Render deployment, and businesses are tenants inside it via `company_id` scoping** (multi-company-in-one-deployment, effectively a SaaS hosting model even though the codebase itself isn't multi-tenant-architected at the infra level). If a business ever needs to run their own fully separate instance later, that's a second Render project pointed at the same codebase — not a code change. Say now if this doesn't match your intent.

---

## 2. Non-Negotiable Architecture Rules

Give these to the agent as fixed constraints, not suggestions:

1. **Every query scoped by `company_id`.** No endpoint may return cross-company data. Enforce via a middleware/mixin, not per-view checks the agent might forget to add.
2. **Offline-first is default behavior**, not a bolt-on: any create/update endpoint used by branch-level staff must be queueable client-side and idempotent server-side (safe to replay).
3. **Payments are manually recorded, never gateway-integrated** (for the Sudan configuration): a `Payment` record stores method (`cash`/`bank_transfer`), the company's receiving bank account, sender bank name, last-4 reference digits, amount, recorded-by, timestamp. No external API calls. A `verified_at` / `verified_by` field exists for later manager reconciliation but never blocks the sale.
4. **Returns are child records of the original document**, never standalone. A `SalesReturn` line always references an `InvoiceLine`; a `PurchaseReturn` line always references a `ReceivingLine`. Quantity returned can never exceed quantity on the original line — enforce this as a DB constraint or serializer validation, not just a UI check.
5. **Returned stock never auto-re-enters sellable inventory.** Every return requires an explicit disposition: `sellable`, `damaged_quarantine`, or `written_off`.
6. **Every return generates a Credit Note (sales) or Debit Note (purchase)** as a distinct, sequentially-numbered document type — modeled as a first-class entity now, even though Sudan-mode only prints it, because Gulf-mode later needs it to carry e-invoicing-compliant fields without a schema rewrite.
7. **Tax/invoice behavior is jurisdiction-pluggable.** Add a `TaxProfile`/`CountryConfig` concept from M1 onward (`country`, `invoice_format`, `e_invoicing_enabled`) even if only a "Sudan: simple" profile is implemented now. Do not hardcode Sudan-only assumptions into the invoice model itself.
8. **Activity Log is mandatory on all state-changing actions**, not just the modules that "seem important." Login/logout, every create/update/delete on Product, Invoice, Payment, Return, User, Permission change, Backup, Restore, Landing page edit — all write to the same audit table.
9. **No corrections via silent edit on financial/audit records.** Payments, Invoices, Returns, Stock Movements are append-only; a correction is a new offsetting entry, never an UPDATE that erases history.

---

## 3. Core Data Model (high-level — agent designs full schema per milestone, this is the shape it must respect)

- **Identity/Org:** `User`, `Role`, `Permission`, `Company`, `Branch`, `Department`
- **Inventory:** `Product`, `Category`, `Brand`, `Unit`, `Warehouse`, `StockBatch` (has `expiry_date`, `lot_number`), `StockMovement` (typed: `sale_out`, `purchase_in`, `adjustment`, `transfer`, `sales_return_in`, `purchase_return_out`)
- **Sales:** `Customer`, `Quotation`, `SalesOrder`, `Invoice`, `InvoiceLine`, `Payment`, `CompanyBankAccount`
- **Purchasing:** `Supplier`, `PurchaseOrder`, `Receiving`, `ReceivingLine`
- **Returns:** `SalesReturn`, `SalesReturnLine` (→ `InvoiceLine`, disposition, reason code), `PurchaseReturn`, `PurchaseReturnLine` (→ `ReceivingLine`, status: `requested/acknowledged/shipped/resolved`), `CreditNote`, `DebitNote`
- **CRM:** `CustomerGroup`, `Lead`, `FollowUp`, `Note`
- **HR:** `Employee`, `Position`, `Attendance`, `LeaveRequest`, `PerformanceRecord`, `EmployeeDocument`
- **Platform:** `ActivityLog`, `SyncQueueItem`, `SyncLog`, `BackupRecord`, `TaxProfile`

---

## 4. What is explicitly OUT of scope for the initial build (do not let the agent add these unprompted)

- Payment gateway integrations of any kind (Sudan mode is manual-only)
- ZATCA/UAE Peppol live integration (stub the `TaxProfile` interface only — Section 5, M11)
- Full general ledger / double-entry accounting (track AR/AP balances at the document level; a full GL is a post-v1 decision)
- Manufacturing/BOM/work orders
- Multi-currency accounting beyond storing a currency + exchange-rate snapshot on transactions

---

## 5. Milestones

### M0 — Scaffolding & Environment
**Build:** Django project + DRF skeleton (with Gunicorn start command), Next.js skeleton (with `next start` production command), `render.yaml` Blueprint defining all 6 services from Section 1's table, `.env.example` for both apps, CI skeleton (lint + test run on push), empty `PROJECT_RULES.md` populated from Section 2.
**Acceptance:** Pushing to the connected Git branch triggers Render to build and deploy `erp-api` and `erp-frontend` natively (no Dockerfile anywhere in the repo); a health-check endpoint responds on the live Render URL; CI runs (even with zero tests) on a dummy PR.

### M1 — Auth, Users, Roles, Company/Branch/Department
**Build:** JWT-via-HttpOnly-cookie auth, `User`/`Role`/`Permission` (role list per Section on user roles: Super Admin, Business Owner, GM, Branch Manager, Inventory/Sales/Purchasing/HR/CRM Officer, Landing Page Manager, Viewer), `Company`, `Branch`, `Department` CRUD, company-scoping middleware (Rule #1), base `ActivityLog` model + login/logout logging.
**Acceptance:** A user in Company A can never retrieve Company B's data via any endpoint, including by guessing IDs. Login/logout appear in Activity Log.

### M2 — Inventory Core
**Build:** Product, Category, Brand, Unit, Warehouse, StockBatch (with expiry), StockMovement ledger, Stock Adjustment, Stock Transfer, barcode/QR field support, low-stock alert logic.
**Acceptance:** Every stock change of any kind produces exactly one typed StockMovement row; stock levels are always derivable by summing movements (no separate mutable "current stock" field that can drift).

### M3 — Sales & POS + Manual Payments
**Build:** Customer, Quotation, SalesOrder, Invoice/InvoiceLine, POS checkout (offline-capable), `CompanyBankAccount` master data, `Payment` model per Rule #3.
**Acceptance:** A sale can be completed fully offline using cash, syncs cleanly later; a bank-transfer payment records bank name + last-4 reference with no external calls; invoice numbering is sequential and gapless per company.

### M4 — Purchasing
**Build:** Supplier, PurchaseOrder, Receiving/ReceivingLine, outgoing payment recording to suppliers (mirrors M3's manual pattern), basic accounts-payable balance per supplier.
**Acceptance:** Receiving stock generates the correct StockMovement type and updates supplier balance correctly.

### M5 — Returns (Sales + Purchase)
**Build:** SalesReturn/PurchaseReturn per Rules #4–6, reason codes, approval threshold config, CreditNote/DebitNote generation, Returns Report.
**Acceptance:** Cannot return more than was sold/received (line-level constraint enforced server-side); a damaged-disposition return never appears in sellable stock; every return has a generated Credit/Debit Note.

### M6 — CRM & HR
**Build:** CustomerGroup, Lead, FollowUp, Note; Employee, Position, Attendance, LeaveRequest, PerformanceRecord, EmployeeDocument.
**Acceptance:** Standard CRUD + role-based visibility (an HR Officer role can't see Sales data, per role list).

### M7 — Offline Synchronization Engine
**Build:** Client-side action queue, `SyncQueueItem`/`SyncLog` models, retry logic, conflict resolution rules **defined per entity** (financial/inventory quantities: field-level merge or flag-for-review, not last-write-wins), sync status dashboard.
**Acceptance:** Two branches offline simultaneously decrementing the same stock batch do not silently corrupt the total on reconnect — conflicts are surfaced, not silently resolved by whichever synced last.

### M8 — Public Website
**Build:** Auto-generated per-company site: profile, logo, catalog, search, categories, featured products, promotions, contact/social/map, SEO, multi-language content, branch locations.
**Acceptance:** Creating a company automatically provisions a working public site with no manual setup step.

### M9 — Reports & Dashboards
**Build:** Inventory/Sales/Purchase/CRM/HR reports, dashboard analytics, Payment Reconciliation report (recorded vs. verified), Returns Report.
**Acceptance:** Every report is scoped correctly by company/branch/role.

### M10 — Backup/Restore, Multi-language, Theme, Security Hardening
**Build:** Manual backup trigger + scheduled backup via `erp-backup-cron` (Render Cron Job), restore, backup verification/history; Arabic/English with RTL/LTR, dynamic content + PDF export translation; Light/Dark/System theme; CSRF protection, secure file upload, password policy enforcement.
**Acceptance:** A restored backup produces a byte-identical functional state; switching to Arabic flips layout to RTL including PDFs; the cron job appears and runs on schedule in the Render dashboard.

### M11 — Localization/Tax-Profile Abstraction (Gulf-readiness scaffold only)
**Build:** `TaxProfile` model live for "Sudan: simple" (configurable flat rate, plain invoice). Stub interface only for Gulf: fields for `e_invoicing_enabled`, `invoice_xml_format`, no live ZATCA/Peppol calls.
**Acceptance:** Switching a company's `TaxProfile` changes invoice output format without touching Invoice/CreditNote model structure.

### M12 — Testing, Hardening, Deployment Verification
**Build:** Test coverage pass on all modules, `render.yaml` finalized covering all 6 services, deployment runbook (env vars, migration step on deploy, rollback procedure), load-test on POS/offline sync paths.
**Acceptance:** A fresh Render project, given the repo and `render.yaml`, stands up all 6 services correctly with one Blueprint deploy — no manual dashboard clicking beyond entering secrets; documented rollback procedure has been tested at least once.

---

## 6. Working Agreement for the Agent

- Small, reviewable commits per feature within a milestone — not one commit per milestone.
- Write tests alongside the code, not after; a milestone isn't "done" without passing tests demonstrating its acceptance criteria.
- If a milestone's scope turns out to require touching a prior milestone's schema, stop and flag it rather than modifying silently.
- Never introduce a payment gateway, external tax API call, or GL/accounting engine without being explicitly asked (Section 4).
- **Never add a Dockerfile, docker-compose.yml, or any containerization config.** Deployment is Render-native only (Section 1). If the agent's default instinct is to containerize for "portability," override it — that instinct is wrong for this project.
