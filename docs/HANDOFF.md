# Handoff — where the work stands (2026-09-16, after PR #43)

Read this first in a new session. It is the human-readable copy of the
session memory (`~/.claude/projects/.../memory/`), which the assistant loads
automatically; this file is the copy that lives with the code.

## State on 2026-09-16 (PRs #30–#43)

| Area | What landed | Where |
|---|---|---|
| SEO phase 1 (#31) | canonical host `vezano.app` (+ www redirect, `enterprise.` kept), per-page metadata, robots, sitemap, JSON-LD, OG image, noindex on the app | `frontend/lib/site.js`, `app/robots.js`, `app/sitemap.js`, `lib/seo.js` |
| SEO phase 2 (#32) | English edition under `/en/` with hreflang; language read from the URL | `lib/locale.js`, `components/HtmlShell.jsx`, `lib/marketingMeta.js` |
| SEO phase 3 (#34) | data-driven content: 5 solutions, 3 guides, 1 comparison, ar+en | `lib/content/*`, `components/marketing/content/routes.jsx` |
| Platform team (#33, #35, #40, #41) | Marketing Manager role; per-area view capabilities; activity log page + API; member page with edit/role/delete | `backend/core/platform_roles.py`, `accounts/platform_team*.py`, `app/(app)/platform-*` |
| Public company pages (#36–#39, #42) | `/s/<slug>/` landing page (cover, logo, products with photos, gallery, hours, map, WhatsApp), owner preview, directory `/s/` with cards, showcase strip on home, `/sitemap-sites.xml`, consent + completeness | `backend/website/public_pages.py`, `templates/website/`, `website/images.py`, `core/public_media.py`, `components/website/*` |
| Tenant people (#41) | `/users/detail/?id=` with history and activity; deactivate, never delete | `accounts/serializers.py` `UserDetailSerializer` |
| SEO control page, phase A (#43) | `/platform-seo`: site-wide verification tags, GA4 id, default share image, extra robots lines; per-path overrides (title, description, noindex, canonical, per language). Django injects them into the served export's `<head>` and into `/s/` pages at request time (60 s cache). Capabilities `platform.seo.view/manage` | `core/seo_inject.py` (pure rewriter + tests), `website/seo.py` (cache), `website/seo_views.py`, `core/frontend.py`, `app/(app)/platform-seo/page.jsx` |

Production: Render, domains done, Search Console verified (domain property),
home indexed. Both sitemaps live. First real company page: `/s/nwafih/`
(owner still needs to upload cover/logo/product photo to become "complete").

## Open threads (next session starts here)

1. PR #43 (SEO control page, phase A) merged 2026-09-16 and verified on production (health 200, `/platform-seo` chunk served).
2. **SEO admin, next phases** — not built: (B) a health dashboard on `/platform-seo` (public paths without overrides, store pages incomplete or opted out, sitemap counts, last deploy time); (C) a redirect manager (old path → new, 301) applied before the catch-all in `config/urls.py`. Editing solution/guide content from the UI stays out of scope (it lives in `lib/content/*`). To add an injected tag: extend `core/seo_inject.py` and its tests, then the `_seo_site.html` include for `/s/` pages.
3. Owner actions still pending: R2 for media backups (now more important: store images live on the Render disk), Sentry, outbound email, VPS for standalone phase C, flip `SUBSCRIPTION_POLICY` observe → enforce.
4. Store-page plan phases 1–4 are done; a custom domain per company page is on the roadmap (needs Render domain slots or a proxy).

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
