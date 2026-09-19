# Handoff — where the work stands (2026-09-20, PRs #64–#131 merged)

Read this first in a new session. It is the human-readable copy of the
session memory (`~/.claude/projects/.../memory/`), which the assistant loads
automatically; this file is the copy that lives with the code.

## Product direction (decided 2026-09-19): Sudan first

Market research on 2026-09-19 (pound above 8,400/USD on the parallel market,
~90% of Omdurman wholesale shops closed over pricing; payments through bank
apps — Bankak, Fawri, O-Cash; internet shutdowns and grid damage; 17% VAT but
traders exempted from zakat/taxes for 2023–2025; no e-invoicing mandate;
zakat on trade goods 2.5% by law) fixed the target: **multi-branch
wholesalers/distributors, pharmacies and barcode retail in Sudan**. Companies
with a formal accounting department are not the target yet (no general
ledger, bank reconciliation or fixed assets — deliberately deferred; the
market does not ask for them now).

The five Sudan priorities and what shipped, one PR per phase, merged on
green after a live check on local dev servers:

| # | Priority | PR | What it is |
|---|---|---|---|
| 1 | Pricing under inflation | #127 | `Product.reference_price` (USD, 4 dp); `Company.reference_currency/exchange_rate/exchange_rate_at` fed by append-only `org.ExchangeRate` (`/api/exchange-rates/`, manager/owner records; Settings "Exchange rate" card); `POST /api/products/reprice/` by rate or percent, sale/cost/both, category filter, rounding step 0.01…1000 half-up, `dry_run` preview; `suggested_price` and a "today: …" drift hint on the inventory list; "Reprice" drawer; reference field on the product form |
| 2 | Bank-app payments | #128 | `CompanyBankAccount.channel` (bank/bankak/fawri/ocash/wallet); `Payment.transfer_reference` (the app's full id, normalised; `reference_last4` derived; same id on the same account refused); POS and collect-payment drawer take sender + reference (**the POS never sent `sender_bank_name`, so POS bank transfers were failing before this**); `POST /api/payments/reconcile/` matches a Bankak/Fawri/O-Cash `.xlsx/.csv` export (Arabic or English headers) by reference then last-4 + amount, `dry_run` preview, apply verifies matched transfers except self-recorded / already verified / amount mismatch; Finance page "Match a bank-app statement" panel |
| 3 | Zakat on trade goods | #129 | `core/hijri.py` tabular Islamic calendar (astronomical epoch, within a day of Umm al-Qura, no dependency); `GET /api/reports/zakat/` (finance report area) = stock at sale\|cost + open-till cash + bank/app balances + receivables (optional `exclude_doubtful=1` for >90 days overdue) − payables, ×2.5%, `hawl_month/hawl_day` → `next_hawl`, CSV; reports page card with pickers kept per device |
| 4 | Thermal receipts | #130 | `Company.receipt_paper` (a4/80mm/58mm) + `receipt_footer` (Settings → Receipt printing), carried in the document `issuer` block (paper omitted when A4); invoice document lists `payments` (method, amount, channel, reference); `ReceiptView` (72 mm / 48 mm, dashed rules, large totals); paper toggle in `DocumentDrawer` remembered in `localStorage` `print.paper`; `PrintSheet` emits `@page { size: 80mm auto }` |
| 5 | Standalone acceptance on Ubuntu | — | **Deferred by the owner on 2026-09-20** ("ناجل لاحقا ترخيص المستقل"): no VPS, and a local VM (Lima) was declined. Do not raise the standalone/licensed track until the owner does |

Also on 2026-09-19/20: #126 `/api/health/` reports `commit` (from
`RENDER_GIT_COMMIT` or `GIT_COMMIT`) so a merge can be proven live; #131 the
Subscription page's "Recent changes" are sentences with `dd/mm/yyyy` dates
instead of event codes and bidi-scrambled dates.

Next Sudan-specific candidates if asked (not started): takings by channel on
shift close; zakat hawl date stored on the company; USD reference on cost;
Bankak QR on the receipt; the subscription renewal form still asks for the
last 4 reference digits rather than the full transfer id.

## Company review and its execution (2026-09-18) — PRs #88–#107

A department-by-department review (method: routes and API helpers never
called from the app, model fields never rendered, status machines with no
UI transition, two screens computing one number differently) found
customers with no CRUD, credit sales with no payment terms, thresholds not
in Settings, dashboard revenue ≠ P&L revenue, AP summed in document
currency, and a long list of API-only features. Executed in order:

- P0 data correctness: #88 customers + terms, #89 verification worklist +
  editable thresholds, #90 one revenue for dashboard and income statement,
  #91 payables in company currency, #94/#102 SQLite integer-division fixes
  in the revenue terms (`RealOnSQLite` in `finance/metrics.py`).
- P1 promised-but-hidden: #93 purchase orders + AP reports, #95 quotations
  and sales orders, #96 budgets + shared expense categories + expense
  threshold, #97 till sign-off history / money ledger / user deactivation /
  cash-flow forecast, #98 attendance register + employee reviews and
  documents.
- P2 operations: #99 password reset + restore from the screen, #100 opening
  balances as documents, #101 refunds through the offline queue.
- Follow-ups: #103 API language follows the screen cookie; #104 role sweep
  (all 11 roles signed in locally; `rbac_read_modules` cross-department
  reference data; POS zero-tender records no payment); #105 barcode scanner
  focus/UPC-A widening/duplicates; #106 refund cap at money actually paid,
  printable documents from party records, Excel/CSV party import
  (`core/party_import.py`); #107 store credit (`Payment.STORE_CREDIT`);
  #108 labelled document party lines.

Production smoke test on the company «إبتكار» passed after #103/#104.

## Offline, email, plans, public orders (2026-09-18/19) — PRs #109–#125

- Offline tiers: #109 every read screen keeps its last-known response
  (IndexedDB `vezano.responses.v1`, `StaleDataBanner`); #110 pull widened
  (orders, bills, employees), attendance offline, service worker precaches
  every app page (the "/org/ shows the POS" bug); #111 sync panel usable.
- Email: #112 bilingual messages (`core/mailer.py::send_bilingual`).
  Production relay is **Brevo SMTP** (Render `EMAIL_HOST_PASSWORD`), sender
  `Vezano <musab@vezano.app>`; Brevo "Authorized IPs" must stay off.
- Security/plans: #113 admin-set passwords audited + `must_change_password`;
  #114 `org.Device` + plan `devices` limit at sign-in + `/platform-companies/`;
  #115 `/platform-finance/`; #116 plan-change requests (prorated upgrades,
  period-end downgrades); #118 add-ons; #119/#124 entitlements bundled with
  every plan; #120/#121 error states on Users and Subscription pages.
  Plan limits are enforced only with `SUBSCRIPTION_POLICY=enforce` on Render.
- Public orders from `/s/<slug>/`: #122 order + branch notification +
  confirm into a sales order; #123 Web Push (off until `VAPID_*` keys are
  set on Render) + notify preferences; #125 bank-transfer payment claims
  with a pay page, confirmation rings the sale through the POS serializer.

## Earlier in the same stretch — PRs #64–#87

#65–#67 PWA install guidance and Render build hygiene; #68 wide tables on
phones; #69 branch-visibility policy registry (`core/branch_policy.py`,
system check `vezano.E002`); #70 transactional email; #72 nightly
ActivityLog archival; #73–#77 first-party visit analytics, funnel, tenant
visit counter, error monitor (`/platform-errors/`); #78 RSC payload
redirect; #79/#80 backups downloadable and stored in the DB when no S3;
#82 collect a debt from the ledger; #83/#84 payroll and advances post to
Expenses; #85 refusals in the user's language; #86/#87 expiry warnings and
batch-tracked receiving.

## Owner actions still pending (unchanged)

Render: `VAPID_PRIVATE_KEY`/`VAPID_PUBLIC_KEY` for push; confirm
`SUBSCRIPTION_POLICY`; optional `BACKUP_S3_*` (R2); Sentry/uptime monitor;
delete the exposed Zoho app password. Code side: Postgres RLS remains an
open decision; standalone track deferred (above).

## Working conventions learned since 2026-09-17

- One feature branch + PR per phase; merge on green with
  `gh pr merge N --merge --delete-branch`; verify live before opening the PR
  and put the proof (numbers) in the PR body.
- `frontend/out` (the committed static export) conflicts on every merge:
  take main's copy, rebuild, commit the export. i18n conflicts are pure
  additions. Placeholders are `{name}` (single braces).
- Arabic-locale dates inside an LTR span get bidi-scrambled ("192026/9/"):
  format digits by hand on receipts and event rows.
- `force_authenticate` caches `user.company`; views that need today's
  company row must read it fresh.
- A worktree needs `backend/.venv` symlinked to the main checkout's venv
  (excluded via `.git/info/exclude`) and a dev `.env` with `DEBUG=True`.
- Local full runs: `DEBUG=1 DJANGO_SECRET_KEY=test-only DATABASE_URL= python
  manage.py test` (SQLite) and `DATABASE_URL=postgres://macbookairm1@localhost:5432/postgres`
  (local Postgres 16); both are the CI legs.

---

# Previous handoff (2026-09-17, review fix stack #56–#63 merged)

## Architecture review fixes (2026-09-17) — PRs #56–#62

A full architecture review (ERP logic, plan-vs-code drift, isolation and
security, SaaS vs standalone, scalability) was delivered on 2026-09-16. Its
top findings are implemented as a stack of PRs, in review priority order.
**All merged to `main` on 2026-09-17** in order #56, #57, #63 (a reopened copy
of #58, which GitHub auto-closed when its base branch was deleted), #59, #60,
#61, #62. Lesson: with a stacked PR, retarget the next PR to `main` BEFORE
deleting the merged base branch, or GitHub closes it.

| PR | Fix | Key files |
|---|---|---|
| #56 | Anonymous path traversal through the frontend catch-all (`/../../backend/.env` was served) → `safe_join` | `core/frontend.py`, `core/test_frontend_containment.py` |
| #57 | Security batch: audit trail no longer stores passwords (+ `core.0005` scrubs old rows); restore `storage_key` scoped to own backups; authority ladder (a Branch Manager cannot demote a GM); refresh-token rotation and session invalidation on password change; per-account lockout; `NUM_PROXIES=1`; default `SECRET_KEY` refused in prod; `/admin/` superuser-only + `ADMIN_ALLOWED_IPS`; medical uploads validated; exports omit hashes | `core/scoping.py`, `accounts/serializers.py`, `accounts/views.py`, `core/admin_gate.py`, `core/test_security_hardening.py` |
| #58 | Correction model (Rule #9): `POST /invoices/{id}/void/`, `Refund` model + `/api/refunds/`, note/bill `void`, `Bill.amount_due()` nets debit notes, payment balance lock, `Customer.credit_limit/credit_hold`, credit sale needs a customer; frontend `finance.approve` capability, VoidDrawer/RefundDrawer | `sales/models.py`, `sales/views.py`, `returns/views.py`, `sales/test_corrections.py`, `components/finance/*` |
| #59 | Stock + costing integrity: raw movement endpoint = adjustments only; transfer availability lock; costing engine (skip transfers, average reset at ≤0, FIFO oversell settle, returns at sale cost); `reason_code` + approval threshold on adjustments; receipts carry business time, currency, rate and roll `cost_price`; PO status derived; tax through `TaxHandler.compute_tax`; currency+rate on purchasing/payment/note documents | `inventory/costing.py`, `inventory/serializers.py`, `purchasing/serializers.py`, `tax/handlers.py`, `inventory/test_costing_integrity.py` |
| #60 | Offline robustness: `useOfflineMutation` awaits the durable write; POS always sends the displayed `unit_price`; provisional receipt; `DiscardedOperation` + `/api/sync/discard/` with a manager badge; `client_uuid` races answer 200; synced ops logged; pull cursor on `received_at` | `components/sync/*`, `sync/views.py`, `sync/test_offline_robustness.py` |
| #61 | Standalone readiness: systemd timers for daily scans and nightly backup (checked by `preflight`), licence signature re-verified at every resolve, deployment mode bound to `Installation`, HTTPS hard-required, `requirements.lock`, SaaS hosts/HSTS preload SaaS-only, gunicorn 3 workers, `run_server.bat` removed, PROJECT_RULES/ARCHITECTURE aligned | `deploy/standalone/*.timer`, `licensing/services.py`, `ops/preflight.py`, `config/deployment.py` |
| #62 | Receivables in SQL: `sales/querysets.py` + `purchasing/querysets.py` used by AR/AP aging, cash-flow, CFO KPIs, debt ledger and the receivables scan (query count no longer grows with invoices); `page_size` param (≤500) and full customer/supplier pickers; composite indexes on StockMovement, Invoice, InvoiceLine, Payment, ActivityLog | `sales/querysets.py`, `sales/debt_queries.py`, `reports/views.py`, `core/pagination.py`, `sales/test_receivables_sql.py` |

**Deploy blocked on 2026-09-17 — owner action needed in the Render dashboard.**
The first deploy after #57 failed in pre-deploy with
`ImproperlyConfigured: DJANGO_SECRET_KEY must be set when DEBUG is False.`
That is the new guard doing its job: the hand-created `erp-api` service (and
probably both cron jobs) has NO `DJANGO_SECRET_KEY`, so production has been
signing JWTs, sessions and sync cursors with the public default key. The old
version keeps serving until this is fixed. To unblock:

1. Render → `erp-api` → Environment: add `DJANGO_SECRET_KEY` = a random
   value of 50+ characters (`python -c "import secrets;print(secrets.token_urlsafe(64))"`).
   Add the SAME value to `erp-backup-cron` and `erp-daily-scans` (they share
   signed data with the web service).
2. Same screen: add `PYTHON_VERSION` = `3.12.3` — the failing log shows the
   service on Python 3.14, which CI never tests — and `WEB_CONCURRENCY` = `3`.
3. Redeploy. Every user is signed out once (tokens signed with the old key
   stop verifying), which is the intended effect.

Deploy notes: production must have `DJANGO_SECRET_KEY` set
(#57 refuses to boot otherwise); migrations `core.0005`, `sales.0010–0012`,
`inventory.0010–0011`, `org.0009`, `purchasing.0004`, `returns.0004`,
`sync.0002`, `core.0006` run in the pre-deploy step; `WEB_CONCURRENCY=3` is
now in `render.yaml` and should be set on the hand-created service too.

Still open from the review (owner decision or separate work): Postgres RLS;
a branch-policy registry for company-wide resources (customers, suppliers,
bills, expenses); an email backend; ActivityLog archival; consolidating the
module list into one registry; the standalone acceptance run on a real
Ubuntu host.

Testing note: the Postgres CI leg catches what SQLite cannot
(`select_for_update` over `select_related` outer joins). A local Postgres 16
recipe is in the session memory (`architecture-review-2026-09.md`).

## State on 2026-09-16 (PRs #30–#55)

| Area | What landed | Where |
|---|---|---|
| SEO phase 1 (#31) | canonical host `vezano.app` (+ www redirect, `enterprise.` kept), per-page metadata, robots, sitemap, JSON-LD, OG image, noindex on the app | `frontend/lib/site.js`, `app/robots.js`, `app/sitemap.js`, `lib/seo.js` |
| SEO phase 2 (#32) | English edition under `/en/` with hreflang; language read from the URL | `lib/locale.js`, `components/HtmlShell.jsx`, `lib/marketingMeta.js` |
| SEO phase 3 (#34) | data-driven content: 5 solutions, 3 guides, 1 comparison, ar+en | `lib/content/*`, `components/marketing/content/routes.jsx` |
| Platform team (#33, #35, #40, #41) | Marketing Manager role; per-area view capabilities; activity log page + API; member page with edit/role/delete | `backend/core/platform_roles.py`, `accounts/platform_team*.py`, `app/(app)/platform-*` |
| Public company pages (#36–#39, #42) | `/s/<slug>/` landing page (cover, logo, products with photos, gallery, hours, map, WhatsApp), owner preview, directory `/s/` with cards, showcase strip on home, `/sitemap-sites.xml`, consent + completeness | `backend/website/public_pages.py`, `templates/website/`, `website/images.py`, `core/public_media.py`, `components/website/*` |
| Tenant people (#41) | `/users/detail/?id=` with history and activity; deactivate, never delete | `accounts/serializers.py` `UserDetailSerializer` |
| Sign-in + presence (#44) | `LoginView` never called `auth.login()`, so `last_login` was always empty; now `accounts/presence.py` fills it at sign-in, `CookieJWTAuthentication` touches `User.last_seen_at` at most every 2 min, `is_online()` = seen within 5 min. Migration `accounts.0004` backfilled both from the audit trail. Team page shows "online now / last seen"; overview has a team card (members with `platform.team.view` only) | `accounts/presence.py`, `accounts/test_presence.py`, `website/views.py` `_team()` |
| Directory cards + services (#45) | `/s/` shows a card for every listed site (placeholder cover in the company colour + initial mark when images are missing; complete sites first); `Website.services` (≤6 lines, ≤60 chars) edited under "ماذا تقدّم", shown as chips on the card and as a strip under the hero; falls back to featured product names; part of completeness | `website/public_pages.py` `site_card()`, `templates/website/public_directory.html`, `website/models.py` `service_lines()` |
| Phone + WhatsApp links (#46) | `PhoneLink` renders any phone as `tel:` + a WhatsApp badge (`lib/phone.js`: `+`/`00` trusted, local `0…` completed with the country's dialling code, SD default). On registration requests (phone now shown, with the request's country), subscriptions (`company_phone`), debts, suppliers, branches, party records | `components/ui/PhoneLink.jsx`, `lib/phone.js`, `tests/phone.test.mjs` |
| Demo requests with phone (#47) | `PlatformLead.phone` + `preferred_channel` (whatsapp default), email optional; public form needs phone or email; landing copy rewritten around the walkthrough; inbox shows call/WhatsApp + "prefers" badge | `website/models.py`, `website/serializers.py` `DemoRequestSerializer`, `components/landing/LandingPage.jsx` |
| Platform contact on the site (#48) | `SeoSettings.support_whatsapp/phone/email` edited on `/platform-seo`; `GET /api/public/site-contact/` (5-min cache); floating WhatsApp button, footer lines and a direct link under the walkthrough form; nothing injected into the export | `website/seo_views.py` `PublicSiteContactView`, `components/marketing/SiteContact.jsx` |
| Follow-ups (#49) | `FollowUpMixin` on leads + registrations (last contact, next follow-up, note); `POST …/contact/` logs `contact` activity from the call/WhatsApp/email links; `?due=1`; badges count due follow-ups; `FollowUpPanel` on both cards | `website/followups.py`, `components/platform/FollowUpPanel.jsx` |
| Media health (#50) | `stored_public_url()` hides images whose file is gone (placeholder + "missing" in completeness); `/api/health/` → `media: {storage: configured|ephemeral, writable, public_files}` | `core/public_media.py` |
| Show-password toggle (#51) | `components/ui/PasswordInput.jsx` on `/login` and `/activate-owner` | |
| Demo seeder (#52) | `manage.py seed_demo --owner <email> [--sales N] [--days N] [--platform] --yes` fills a company (catalogue, stock, customers/debts, suppliers, CRM, complete published page with generated tiles, POS sales through the real checkout view) and optionally the platform inbox. Never takes a password; run from the Render shell | `core/management/commands/seed_demo.py` |
| Plans console (#54, #55) | Module picker (`lib/planModules.js` mirrors `core/rbac.py` codes + `PlanVersion.clean()` dependencies); `PlanEditor` edits every plan + version field, and pricing/modules/limits changes publish a new version because published versions are immutable; the public pricing card expands `["*"]` to all module names. `seed_demo` regenerates lost cover/logo/product tiles (#53) | `app/(app)/platform-plans/page.jsx`, `components/platform/ModulePicker.jsx`, `components/marketing/PlanCards.jsx` |
| SEO control page, phase A (#43) | `/platform-seo`: site-wide verification tags, GA4 id, default share image, extra robots lines; per-path overrides (title, description, noindex, canonical, per language). Django injects them into the served export's `<head>` and into `/s/` pages at request time (60 s cache). Capabilities `platform.seo.view/manage` | `core/seo_inject.py` (pure rewriter + tests), `website/seo.py` (cache), `website/seo_views.py`, `core/frontend.py`, `app/(app)/platform-seo/page.jsx` |

Production: Render, domains done, Search Console verified (domain property),
home indexed. Both sitemaps live. First real company page: `/s/nwafih/`
(owner still needs to upload cover/logo/product photo to become "complete").

## Open threads (next session starts here)

1. PRs #43 (SEO phase A), #44 (sign-in/presence), #45 (directory cards + services), #46 (call + WhatsApp links) #47 (demo requests with phone + preferred channel), #48 (platform contact on the site), #49 (follow-ups), #50 (media health), #51 (show password), #52 (seed_demo), #53 (seed_demo lost files), #54 (module picker) and #55 (full plan editor) merged 2026-09-16; #55's Render deploy was still pending when the session ended — check `/platform-plans/` references chunk `page-1de4affcbc3501ee.js`. Owner asked for both on 2026-09-16 after seeing "never signed in" on the team page and a text-only entry for نوافح in the directory. Nwafih's owner can now fill "ماذا تقدّم" in the site editor; until then the card shows the featured product names.
2. **SEO admin, next phases** — not built: (B) a health dashboard on `/platform-seo` (public paths without overrides, store pages incomplete or opted out, sitemap counts, last deploy time); (C) a redirect manager (old path → new, 301) applied before the catch-all in `config/urls.py`. Editing solution/guide content from the UI stays out of scope (it lives in `lib/content/*`). To add an injected tag: extend `core/seo_inject.py` and its tests, then the `_seo_site.html` include for `/s/` pages.
3. Owner actions still pending: R2 for media backups (now more important: store images live on the Render disk), Sentry, outbound email, VPS for standalone phase C, flip `SUBSCRIPTION_POLICY` observe → enforce.
4. **Contact model — only outbound sending remains**: email provider (Resend/SES) for confirmations, activation links and invoices; WhatsApp Cloud API later. Needs the owner's pick and an account. Items 1–3 shipped (#47–#49).
5. **Demo data on production**: owner asked to fill the demo tenant (aramkoo555@gmail.com) and the subscriptions inbox; the assistant does not sign in with owner passwords, so the owner runs `python manage.py seed_demo --owner aramkoo555@gmail.com --platform --yes` in the Render shell of the web service (MEDIA_ROOT must be the disk first — see 6). Credentials were pasted in chat on 2026-09-16; rotate them.
6. **Media on production**: after #50, `/api/health/` reports `media.storage = "configured"`, `writable = true`, `public_files = 0` — MEDIA_ROOT (`/var/data/media/`) is right now, but the نوافح cover/logo uploaded earlier are gone (404), so the card shows the placeholder. Owner re-uploads from the site editor; watch `public_files` grow and survive the next deploy. R2 backups still pending.
7. Store-page plan phases 1–4 are done; a custom domain per company page is on the roadmap (needs Render domain slots or a proxy).

## How to continue in a fresh session

Say: "اقرأ docs/HANDOFF.md وواصل من النقطة 2" (or the number you want).
The assistant's memory index (`MEMORY.md`) already points to the detailed
notes per area: `seo-admin-plan`, `seo-plan-status`, `platform-team-roles`,
`public-company-pages`, `review-followups`, `vezano-deploy-facts`,
`working-style`.

---

# Earlier handoff (2026-09-14, after PR #15)

Read this first in a new session. It is the human-readable copy of the
session memory; the plan and decisions below are already agreed with the owner.

## Delivered and merged today (PRs #3–#12)

| Area | What landed |
|---|---|
| Review fixes, phase 1 | POS tax, token refresh, payment cap, cash-shift guard, Postgres in CI |
| Phase 2 | business time (`issued_at`/`created_at`/`recorded_at` client-supplied, `received_at` audit), numbered credit/debit notes, cost snapshot on sale, half-up rounding, single currency |
| Phase 3 | real offline POS: service worker, cached session, IndexedDB mirror via `sync/pull`, reachability probe, offline banner, local receipt reference |
| Phase 4 | every branch-level write queues offline (`useOfflineMutation`); inventory screens degrade to the local mirror |
| Phase 5 | FEFO batches at sale, line/ticket discounts, daily scans (cron), stock alerts, periodic stock count with approval, accessible fields, pack units (carton/strip) |
| Deploy | `preDeployCommand` migrations, `erp-daily-scans` + `erp-backup-cron` cron jobs, `SUBSCRIPTION_POLICY=observe`, services are hand-created (no Blueprint) — see `DEPLOYMENT.md` |
| Standalone A | `license_keygen`, `issue_license`, version ceiling enforced, `AccessBanner`, licence page with upload; rejected imports are 400 |
| Standalone B | `StandaloneSurfaceGate` (SaaS routes 404 on customer installs), support-friendly `/api/health/`, root → login on standalone |

## Standalone phase C — done locally (PR #13), pending on a real host

The whole runbook was run literally against local PostgreSQL 16 (no VPS, no
Docker on this machine): package → verify → unpack → venv → migrate →
bootstrap → `create_owner` → Gunicorn → licence import → POS sale + offline
replay → browser login through the served export → `backup.sh` →
`restore.sh` into an empty DB → `upgrade.sh` 1.0.0→1.0.1. Every break was
fixed in the scripts; the acceptance table is in `OPERATIONS.md`.

Breaks fixed: dev `.env`/`.claude`/`.pytest_cache`/sqlite backup shipped in
the archive; `.sha256` not `sha256sum -c` readable; JSON public-key line
died under `. vezano.env` (backup.sh crashed) → `VEZANO_ENV_FILE` read by
Django + `VEZANO_LICENSE_PUBLIC_KEYS_DIR`; `upgrade.sh` venv path; no way
to create the first owner → `manage.py create_owner`. Venv now lives inside
each release (`<release>/venv`), units use `/opt/vezano/current/venv`.

**Still open for phase C:** the same run on a clean Ubuntu 24.04 host —
systemd units, Caddy TLS (`Caddyfile.example`), distro PostgreSQL, a browser
going offline and back. Needs a VPS from the owner.

## Standalone phase D — done locally (PR #14)

Upgrade 1.0.0 → 1.1.0 with a real migration (`licensing.0003`, the
installation now records `previous_version`/`upgraded_at`; `upgrade.sh`
records the version after the link moves), then `rollback.sh` (new): restore
the pre-upgrade backup into a fresh DB + media dir, verify, repoint
`vezano.env`, move `current` back, preflight. Found and fixed: `restore.sh`
exited 1 after a successful restore with `--media-root` (EXIT trap + `set -e`).
`VERSION` in the repo is still 1.0.0 — bump it when cutting the real 1.1.0.

## Standalone phase E — done (PR #15)

`deploy/standalone/CUSTOMER_GUIDE.ar.md` (customer, Arabic),
`SHIP_CHECKLIST.md` (vendor gates: ship / never-ship / issue / never-issue),
`LICENCE_TERMS.md` (perpetual + maintenance, term → grace → read-only,
no-data-loss clause; each term mapped to the `issue_license` flag and the
runtime state). Counsel still has to turn the terms into a contract.

**The one thing left on the standalone plan:** phase C on a real Ubuntu
24.04 host (systemd, Caddy TLS, distro PostgreSQL, browser offline/online)
— needs a VPS from the owner. `OPERATIONS.md` is the exact sequence; the
acceptance table there is where the result goes.

## Operator reminders

- Every `render.yaml` change must be copied into the Render dashboard by hand.
- Move `SUBSCRIPTION_POLICY` to `enforce` after a few days of clean
  `subscription_observe` / `subscription_capacity_observe` log lines.
- Never run `npm run build` while `next dev` is up (it clobbers `.next`).

## To resume in a new chat

> نفّذ المرحلة C على VPS حقيقي: <العنوان> — ssh <المستخدم>@<العنوان>

Add the VPS address and SSH access in the same message if one exists.
