# Session Handoff Plan

Generated at the end of a long working session. Reflects the **verified** state
of the repo (checked against code and a full test run), not assumptions.

---

## 1. Project / Task Summary

**Multi-company (multi-tenant) ERP platform**, hosted centrally — businesses are
tenants isolated by `company_id`, not self-hosted installs.

| Layer | Stack | Location |
|---|---|---|
| Backend | Django 5 + DRF, cookie-JWT auth, SQLite (dev) / Postgres (prod) | `backend/` |
| Frontend | Next.js App Router, **static export**, Tailwind, bilingual AR/EN | `frontend/` |
| Jobs | Celery (`erp-worker`) | `backend/config/celery.py` |
| Deploy | Render Blueprint, **native runtimes, no Docker ever** | `render.yaml` |

**Serving model: monolithic.** Django serves the built Next.js static export
(`frontend/out`) from the same origin — one deployable web service, no CORS hop
in production. See `backend/core/frontend.py`.

**Scale:** 15 Django apps, ~67 models, **401 backend tests passing**
(`cd backend && venv\Scripts\python -m pytest` — use pytest, **not**
`manage.py test`: `conftest.py` clears the login-throttle cache between tests
and the Django runner ignores it, so the suite cascades into ~130 false
failures).

---

## 2. Completed Work

### Infrastructure & serving
- Installed all backend (venv) + frontend (npm) dependencies.
- **Monolithic serving**: Django serves the Next static export; `render.yaml`
  collapsed from 6 services to 5 (frontend builds inside `erp-api`).
- Added `FORCE_HTTPS` setting — decoupled from `DEBUG` so `DEBUG=False` can be
  run locally over plain HTTP without the SSL-redirect/HSTS trap.
- `frontend/.env.production` pins `NEXT_PUBLIC_API_BASE_URL=/api` (relative, so
  it works on any hostname).

### Internationalisation & UI
- Full i18n: `lib/i18n.js` catalogue + `I18nProvider`, **localStorage + cookie**
  persistence, RTL, **Cairo** (body) / **Tajawal** (headings) for Arabic.
- Role names localised via `translateRole()`; Arabic terminology **مسؤول → مدير**.
- Mobile-first `AppShell` (drawer nav), public marketing landing page at `/`.

### Modules built or extended
- **CRM** (new): CustomerGroup, Lead + pipeline stages, FollowUp, Note.
- **HR** (extended): `Position.base_salary`; typed leave (annual/casual/unpaid/
  sick/other); **sick leave with real medical-report file upload** served only
  through a company-scoped action; SalaryAdvance, WorkPolicy, Deduction.
- **Finance** (new): Expense, `Finance Department` role, finance dashboard.
- **Inventory**: inline create for category/brand/unit (killed dead dropdowns),
  brand/unit/barcode on the product form, stock transfers, movement history.

### Barcode system
- Conditional `unique(company, barcode)` (ignores blanks) — a scan can never
  resolve to two products.
- `GET /products/by-barcode/?code=` **exact match only** (never fuzzy).
- HID-scanner input component wired into **POS, Receiving, and Returns**
  (returns validate the scan belongs to the selected invoice — Rule #4).
- Internal **EAN-13** generation (GS1 prefix `2`, per-company sequence, check
  digit) + hand-written EAN-13 SVG renderer (**no new npm dependency**).
- `/labels` bulk label printing page; offline product cache for scanning.

### Security, audit & records
- **Access-control audit: no vulnerabilities.** Cross-role access empirically
  denied (403s); dashboard returns only permitted sections; sync ops are
  RBAC-checked per operation.
- **Audit Logs page** (`/logs`) — admin-only (`IsAuditViewer`), filters by user/
  action/entity/date, shows **before → after** diffs.
- Dashboard **branch scoping** fixed (a branch manager saw company-wide totals).
- **Customer & Supplier 360° records pages** — full chronological timeline,
  status, filters, CSV export, RBAC-gated, view/export audited.

### Financial controls (Level 1 + 2)
- `payment_terms_days` + `due_date` on Invoice **and** Bill → aging now measures
  *lateness*, not age since issue.
- Reports added: **income statement, cash flow, receivables worklist,
  payables-due, CFO KPIs, cash-flow forecast**.
- **Segregation of duties**: the recorder of a payment cannot verify it.
- **`Chief Financial Officer` role** (controls money, deliberately cannot write
  sales/purchasing) + `payment_approval_threshold` on Company: payments at/above
  it require an approver role. SoD still outranks approval authority.
- `CanVerifyPayment` permission — verification treated as a treasury function.
- **Bank balances** derived (opening + in − out); **Budgets** (category-level)
  with CFO-gated approval and variance reporting.

### Deletion policy + navigation (latest round)
- **Three-tier deletion policy** (`backend/core/deletion.py`). Tier A never
  deletable (Expense, Deduction, approved Budget, decided SalaryAdvance) —
  405 naming the correcting action. Tier B archives via the **existing**
  `is_active` flag, so no migration (Customer, Supplier, Product, Warehouse,
  Category, Brand, Unit, Position, WorkPolicy, CustomerGroup, Branch, Bank
  account, User; Employee → `terminated`). Tier C hard delete, manager-only.
- **Hard delete now requires a manager-level role** by default
  (`rbac.DELETE_ROLES`), with `manager_only_delete = False` opting out the
  places where removing a row is ordinary work (website sections, CRM
  notes/follow-ups, attendance, leave requests).
- **Users are deactivated, never deleted** — `Payment.recorded_by/verified_by`
  are SET_NULL, so deleting a user used to strip the names off every payment
  they handled, silently voiding the segregation-of-duties evidence. Also
  blocked deactivating your own account.
- `ProtectedError` → **409 naming what blocks the delete**, instead of a 500
  (`core/exceptions.py`, wired via `EXCEPTION_HANDLER`).
- **Nested sidebar**: 17 flat entries → 9 top-level with 4 groups; empty groups
  are pruned per-role, the group holding the current page auto-expands, and the
  open/closed state persists in localStorage.
- **Roles grouped, not merged**, in the user form (`frontend/lib/roles.js`) —
  five families plus a one-line plain-language description per role. Fixed
  `Chief Financial Officer` missing from `ROLE_KEY`, which left it untranslated.

### Printable documents (latest round)
Before this there was **no invoice printing anywhere** — the only `window.print()`
in the app was `/labels`. Added:
- **Company issuer fields** (`address`, `phone`, `email`, `tax_number`,
  `registration_number`) + migration `org.0004`. Without these a printout is a
  receipt, not a tax invoice.
- **`GET /api/company/profile/`** — a business edits its own printed identity
  without a platform admin. Deliberately separate from `CompanyViewSet`, which
  stays platform-admin-only for the tenant root (slug, is_active).
- **`core/documents.py`** — shared builders. Blank fields are omitted, never
  printed as empty labels; all money goes through one 2-decimal formatter.
- Document endpoints: invoice (enriched with dates, paid/due, issuer, branch),
  **credit note**, **debit note**, **payment receipt**, **supplier payment
  voucher**.
- **`components/print/`** — `DocumentView` (one component for preview *and*
  paper) + `PrintSheet`, which portals the print copy out to `<body>` because a
  Drawer clips at one screenful. Print rules are scoped to the component so they
  can't break `/labels`.
- Wired into: invoice list, POS after-sale, and a new **credit/debit notes tab
  on Returns** — closing a real Rule #6 gap where the system issued notes that
  nobody could see or hand over.
- No new npm dependency: browser print + `@media print`, which handles Arabic
  RTL for free.

### Returns module split (latest round)
`returns` became **`sales_returns` + `purchase_returns`**. A purchasing officer
could previously disposition *customer* returns — the decision that puts goods
back into sellable stock — because both sides shared one module.
- Role matrix: Sales Officer holds `sales_returns` only, Purchasing Officer
  holds `purchase_returns` only; managers keep both.
- `APP_MODULE` no longer maps the `returns` app (one app, two authorities), so
  **every viewset in it must declare `rbac_module`** — `RoleModuleAccess` treats
  an unresolvable module as "not module-scoped" and waves the request through.
  `test_every_returns_viewset_declares_its_module` guards that.
- Credit notes follow the sales side, debit notes the purchasing side; the sync
  op registry and the dashboard tile were split to match.
- Frontend: `nav.js` gained `altModule` so the Returns link shows for either
  side, and the page gates its own tabs.

### Audit log review (latest round)
- Log rows now carry **`user_role`** (joined via `user__role` in the viewset, so
  no N+1). The page shows **name over role, email as a subtle third line** —
  "who did this" needs authority, not just an address. Search matches full name
  too.
- The page previously handled **5** action types and rendered only
  `metadata.changes`; the system emits **11** actions with varied metadata. The
  new `Details` renderer turns each shape into one plain-language line (export
  counts, approvals, verified-by, changed fields, dispositions, lead
  conversions, status changes) with a scalar fallback so nothing meaningful
  shows as a bare "—". Added tones/labels for archive/unarchive/export/approve.

### Shop mode (latest round)
`Company.business_type` (`shop` | `enterprise`, default **enterprise** so no
existing tenant loses screens on upgrade). Migration `org.0005`.
- **A presentation preset, never a permission.** It hides nav entries; the RBAC
  matrix, scoping and every invariant are untouched, and hidden pages still
  answer over the API. Two tests pin exactly this (`access_map` identical before
  and after; hidden modules still return 200) — if it ever became an access
  control, growing out of shop mode would turn from a toggle into a migration.
- Shop mode hides CRM, HR, website, org, party records and label printing.
- **Single-child groups are flattened** into the page itself — a group wrapping
  one link is an extra click for nothing. Applies to every role, not just shops
  (a Website Manager now sees `Website` directly instead of `Administration ▸
  Website`).
- `business_type` is returned by `/auth/me/` so the shell paints the right nav
  on first render instead of rearranging a moment later.
- **Auto-SKU**: `POST /products/` with a blank `sku` allocates `P000001…` using
  the same row-locked per-company counter as internal barcodes, skipping values
  already taken by hand. Only on create — regenerating on edit would invalidate
  a shelf label already printed.
- POS hides the warehouse picker when the company has only one.
- 21 tests in `org/test_shop_mode.py`; nav preset covered by 40 checks in the
  `verify_nav.mjs` harness.

### Making shop mode discoverable (latest round)
Shop mode existed but **nothing ever offered it**: `business_type` defaulted to
`enterprise`, so every new tenant landed in the full 17-page layout and would
only have found the simpler one by opening a settings form they had no reason
to open. A feature nobody is offered is a feature nobody has.
- **`Company.business_type_chosen`** (migration `org.0006`) makes "inherited the
  default" distinguishable from "actually decided". **Backfilled `True`** for
  existing companies — they have been trading in their layout, so it is a
  settled decision, not an unanswered question.
- **First-run prompt** (`components/SetupPrompt.jsx`): a one-time,
  non-dismissable choice between *single shop* and *multi-branch business*,
  shown only to someone with `settings: write` — a cashier is not blocked by a
  question that is not theirs. Picking either value (including confirming
  `enterprise`) settles it. The flag is **read-only over the API**, so the
  question cannot be dismissed without being answered.
- **Shop-mode badge** in the sidebar linking to Settings: shop mode hides seven
  pages, and without a marker their absence reads as a fault rather than a
  setting, with no trail back to the switch that caused it.
- **Django admin** now lists and filters by `business_type` /
  `business_type_chosen`, so whoever provisions tenants can see the split
  without opening each record.
- `AuthProvider` gained **`refresh`** (exposes `loadSession`) so the nav
  reshapes immediately after the choice. It did not exist before — the call I
  first wrote would have silently done nothing.

**When self-signup lands, the choice belongs on the signup screen** and this
prompt becomes the fallback for tenants provisioned by an admin.

### Grocery till improvements
- **Sell by weight**: cart quantity is now a typed decimal input (kept as a
  *string* in state — coercing to a number per keystroke eats a trailing dot
  and makes weights unenterable). +1/−1 buttons remain for whole units. The
  backend already took 3 decimals; only the UI was the blocker.
- **Price override at the counter**: editable per line, sent as `unit_price`
  **only when actually changed**, so untouched lines still follow the catalogue.
  The original price is shown beside the changed one. Overriding never edits
  the product.
- **Change due**: the amount box now means *cash received*; the payment is
  **capped at what is owed** and the surplus shown as change. Previously
  entering the tendered amount would have recorded an overpayment and left a
  phantom credit on the customer.
- **`Product.is_stock_tracked`** (default True, migration `inventory.0004`) for
  bags, delivery charges, and a catch-all "miscellaneous" line — selling one
  posts **no stock movement** and it stays out of low-stock. Combined with the
  price override, this is how a shop rings up an item that isn't in the
  catalogue.
- Fixed a latent bug found while restructuring: the POS offline-fallback path
  rebuilt its payload separately and had **drifted — it omitted the shift**, so
  a sale recovered from a flaky connection belonged to no drawer. Both paths now
  share one payload.
- 15 tests in `sales/test_pos_grocery.py`.

**Known limitation:** the POS computes change against the pre-tax subtotal (the
client doesn't know the tax rate; tax is applied server-side). Correct for the
0% case most small shops run, understated where a tax rate is configured.

### Till sessions & cash drawer
The biggest functional gap for small shops: there was **no shift or drawer model
at all**, so "where did the 500 go?" was unanswerable — every other money path
names a person, notes in a drawer name nobody.
- **`CashShift`** (`sales/models.py`): opened with a counted float, closed with a
  physical count. `expected_cash` is **derived** (float + cash takings + drawer
  movements), never stored. **Bank transfers excluded** — they never reach the
  drawer. Partial unique constraint enforces **one open shift per person**
  (two would make every takings figure ambiguous).
- **`CashDrawerMovement`**: signed, append-only cash in/out for refunds, safe
  drops, petty cash, float top-ups, corrections. Without it a walk-in refund
  hands money back with nothing recording it and the drawer can never
  reconcile. Sign is validated against the kind so a typo can't book a refund
  as a deposit and hide a shortfall.
- **`Payment.shift`** (nullable) — the till sale's drawer. Sent by the client,
  not inferred from the clock, so an offline sale that syncs after its shift
  closed still lands in the drawer that took the cash. Shifts stay **optional**:
  an existing deployment can keep selling without ever opening one.
- **Close is one-time** (Rule #9) — no reopen; a miscount is corrected by a
  drawer movement. The variance is written to the audit log.
- **`review` requires a manager and forbids self-review** — the person who
  counted cannot also accept the count, same principle as payment verification.
- Frontend: `components/sales/CashDrawer.jsx` + a **Till** tab. The expected
  figure is **hidden until the count is entered**, so counting doesn't degrade
  into confirming. The POS warns (but does not block) when no drawer is open.
- 41 tests in `sales/test_cash_shift.py`.

### Live-data audit + oversight fixes
Audited all 14 real users × 23 endpoints programmatically (DRF
`force_authenticate`, no passwords). **Zero 500s; every 403 landed correctly** —
the sales/purchase returns split verified against real accounts. Four fixes:
1. **Two roles were swapped in the data** — `salesmg@` held Purchasing Officer
   and `bumg@` held Sales Officer. Corrected. (This is what made it look like
   "the purchasing manager sees sales returns".)
2. **Cross-tenant accounts**: `plaformng@` (platform-scoped role) detached from
   its company; `musa2@`'s misleading Business Owner role removed. **`is_superuser`
   was deliberately left alone on `musa2@`** — clearing it could lock the owner
   out of Django admin, and superuser alone is what grants its platform access.
3. **Website Manager had a completely blank dashboard** — added a `website`
   section (publish status + section count).
4. **Audit log was gated on `settings: write`**, which shut out the General
   Manager. Now an explicit `AUDIT_VIEWER_ROLES` (Super Admin, Business Owner,
   General Manager) via `can_view_audit_log`. Officer roles and the **CFO stay
   denied** — the CFO is a subject of the trail, not its reader. `nav.js` gained
   `auditViewer` so the sidebar mirrors the server exactly.

### Bugs found and fixed
- `PurchaseReturnWriteSerializer` had `queryset=None` → crashed URLconf.
- Django admin 500 → `collectstatic` had never been run.
- Platform admin creating company-scoped rows → **500** → now a clean 400.
- `stock-movements` ignored its `?product=` filter (returned every product's).
- **`User.get_full_name()` doesn't exist** (the field is `full_name`) — DRF's
  `default=None` silently swallowed it in **6 serializers**, so user names never
  displayed anywhere. Fixed across core/crm/finance/hr.

---

## 3. Current State & Next Steps

### Where we stopped
CFO **Level 2 backend is complete and tested**; its **UI was not built**. The
deletion policy and the nested sidebar shipped after that (see above).

**Not visually verified:** the logged-in sidebar was checked by asserting the
real `visibleNav`/`groupRoles` logic against role fixtures (15 + 11 checks, all
passing) and by confirming the new strings ship in the build — not by driving
the browser, since that needs a password typed into a login form.

### Immediate next steps (pick up here)
1. **Build Level 2 screens** — budgets (create/approve/variance) and bank
   balances. APIs are done and tested: `/api/budgets/`, `/api/budgets/{id}/
   approve/`, `/api/budgets/{id}/variance/`, `/api/bank-accounts/`,
   `/api/reports/cash-flow-forecast/`.
2. **Expose `payment_approval_threshold` in Settings UI** — it defaults to `0`
   (second approval tier **disabled**) and is currently only settable via Django
   admin/API. Until set, the CFO approval gate does nothing.
3. **Surface archive vs. delete in the UI.** The backend now archives instead
   of deleting, but the frontend still labels the action "Delete" and offers no
   "show archived" filter. Until that lands, an archived row simply looks gone.
4. **Remaining documents with no print path**: purchase order, goods receipt,
   quotation, sales order. The pattern is now established — a builder in
   `core/documents.py`, a `document` action, and a `DocumentDrawer` — so each
   is a small repeat. Quotations and sales orders also still have no UI at all.
   A company logo is also not supported (needs upload + media serving).
4. Deferred by choice: turning `APPROVER_ROLES` / `DELETE_ROLES` from hardcoded
   name sets into flags on `Role`, so approval authority becomes data rather
   than code. Needs a migration and touches the seeded-role mechanism.
5. Optional: **Level 3** — General Ledger, balance sheet, accounting periods,
   monthly close. **Explicitly out of scope** per the build plan ("post-v1
   decision") — needs a conscious decision to reopen.

### Known outstanding issues (pre-existing, not blocking)
- `accounts.0002_alter_user_groups` migration drift — a Django-version artifact
  on the auth `groups` field. **Will fail CI's `makemigrations --check`.** Not
  caused by this session's work.
- `backend/scripts/repo_audit.py` splits paths on `/`, so it reports false
  "broken migration" failures on Windows. CI (Linux) is unaffected.
- Two data-hygiene items: `musa2@gmail.com` is a superuser with no company but
  holds the Business Owner role; `plaformng@gmail.com` has the platform-scoped
  Super Administrator role while pinned to company 1.

---

## 4. Key Technical Context & Constraints

### Non-negotiable project rules (`PROJECT_RULES.md`)
1. **Every query is company-scoped** — enforced by `CompanyScopedQuerySetMixin`,
   never ad-hoc per view.
2. **Offline-first** — POS must work offline; writes are idempotent via
   `client_uuid`.
3. **Payments are manual only. Never integrate a payment gateway** — no external
   API calls for payments (bank *file* import would be acceptable; a bank API is not).
4. **Returns reference the original document line**, never just a product.
5. Returned stock never silently re-enters sellable inventory.
6. Every return generates a Credit/Debit Note.
7. Tax behaviour is jurisdiction-pluggable (`TaxProfile`).
8. **Every state-changing action writes to `ActivityLog`.**
9. **Financial records are append-only** — corrections are new offsetting rows.
- **Never add a Dockerfile or any containerisation config.**
- **Full GL / double-entry accounting is explicitly out of scope** (post-v1).

### Architectural invariants
- **Stock is always derived** by summing `StockMovement`; there is no stored
  quantity field. Same for AR/AP balances and all report figures — nothing
  stored can drift.
- RBAC is **module-level** (`core/rbac.py`): role → module → `write`/`read`/
  `none`, enforced globally via `DEFAULT_PERMISSION_CLASSES`.
- `Role.scope_level` (`platform`/`business`/`branch`) controls data breadth and
  is why **Business Owner ≠ Super Administrator** despite identical module perms.
- Roles are a **fixed seeded set** (`seed_roles`, 13 roles) re-created on every
  deploy — deleting a role in the DB alone is futile.

### Local dev workflow (monolithic mode — currently active)
`backend/.env` has `DEBUG=False`, `FORCE_HTTPS=False`.

```bash
cd frontend && npm run build          # after ANY frontend change
cd backend && python manage.py runserver 8000   # restart after ANY backend change
```

- Use **`http://localhost:8000`** — not `127.0.0.1` (Firefox cached an HSTS
  policy for that IP and force-upgrades it to HTTPS, which fails).
- Run `collectstatic` after switching to `DEBUG=False` or Django admin 500s.
- **App login:** `owner@mycompany.com` / `Owner123456` (Business Owner).
  `musa2@gmail.com` is a platform admin and **cannot create tenant data**.

---

## 5. New Chat Starter Prompt

> I'm continuing work on my multi-tenant ERP platform at
> `C:\Users\Sting\Desktop\erp-sting\erp-platform`. Please read
> `docs/SESSION_HANDOFF.md` first — it has the full state from my previous
> session, including completed work, constraints, and known issues.
>
> **Stack:** Django 5 + DRF backend (`backend/`), Next.js App Router static
> export frontend (`frontend/`), served monolithically by Django on port 8000.
> Bilingual AR/EN with RTL. 228 backend tests currently pass.
>
> **Where we stopped:** CFO financial controls "Level 2" backend is complete and
> tested (budgets with CFO-gated approval + variance, derived bank balances,
> weekly cash-flow forecast) but **none of it has a UI yet**.
>
> **What I want next:** build the Level 2 screens — a budgets page
> (create → approve → variance) and bank balances — matching the existing
> bilingual, mobile-first component patterns. Also expose
> `payment_approval_threshold` in the Settings page, since it defaults to 0 and
> currently disables the CFO approval tier.
>
> **Important constraints:** never add Docker; no payment-gateway integration;
> no general ledger (explicitly out of scope); keep everything company-scoped;
> financial records stay append-only. After frontend changes run
> `npm run build`, and restart `runserver` after backend changes — I'm in
> monolithic mode. Use `http://localhost:8000` (not 127.0.0.1) and log in as
> `owner@mycompany.com` / `Owner123456`.
