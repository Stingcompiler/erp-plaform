# Deployment Runbook

The ERP platform deploys to **Render** as a Blueprint — all services run
natively from source. **There is no Docker anywhere** in this repo, by design
(`PROJECT_RULES.md`).

## Services (from `render.yaml`)

`erp-api` is a monolith: Django/DRF and the built Next.js frontend are one
deployable web service (see `backend/core/frontend.py`) — there is no separate
frontend service, so there's nothing to CORS-wire together in production.

| Service | Type | Runtime | Notes |
|---|---|---|---|
| `erp-api` | web | Python | Django + DRF via Gunicorn; also builds and serves the Next.js static export; health check `/api/health/` |
| `erp-worker` | worker | Python | Celery worker |
| `erp-backup-cron` | cron | Python | nightly `run_scheduled_backup` (02:00 UTC) |
| `erp-cache` | keyvalue | — | managed Redis-compatible; Celery broker |
| `erp-db` | database | — | managed PostgreSQL |

The paid PostgreSQL database is injected into all three Python services as
`DATABASE_URL`. The paid persistent disk is attached to `erp-api` at
`/var/data/media/`, and `MEDIA_ROOT` points Django's protected uploads there.
The disk is for uploaded media; PostgreSQL remains the source of truth for
application records.

## First deploy

1. Push this repo to GitHub.
2. In Render: **New → Blueprint**, select the repo. Render reads `render.yaml`
   and provisions all five components.
   - The web service answers on three custom domains, all of which must be
     added to `erp-api` in Render (**Settings → Custom Domains**) and verified
     so a managed TLS certificate is issued for each:
     - `vezano.app` — the canonical host. Every marketing page's canonical
       tag, the sitemap and the Open Graph URLs point here. It is an apex
       domain, so at the DNS provider use an ALIAS/ANAME record (or the A
       record Render shows for apex domains), not a CNAME.
     - `www.vezano.app` — CNAME to the `erp-api` Render hostname.
     - `enterprise.vezano.app` — the original host. Keep it: existing
       customers have cookies and installed PWAs on it, and it keeps working
       without any redirect.

     The three hosts are always in `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`
     (config/settings.py `VEZANO_PUBLIC_HOSTS`); `DJANGO_ALLOWED_HOSTS` only
     needs `.onrender.com`. Leave `AUTH_COOKIE_DOMAIN` unset so each host keeps
     its own host-only auth cookie.
   - Confirm the existing `erp-api` disk is mounted at exactly
     `/var/data/media/`. Render disks are attached to one runtime service, so
     it belongs on `erp-api`, which receives and serves the protected uploads.
   - Confirm the purchased PostgreSQL resource is named `erp-db` in the
     Blueprint. Render then injects its private `connectionString` into
     `DATABASE_URL` for `erp-api`, `erp-worker`, and `erp-backup-cron`.
   - **Verify the `erp-cache` block** renders as a Key Value store in the plan
     preview. Render's schema for managed Redis/Key Value has changed over
     time; if the preview rejects `type: keyvalue`, consult current Render docs
     and adjust that one block (the rest is standard).
   - **Verify Node/npm are available during `erp-api`'s build.** Its
     `buildCommand` runs `npm install && npm run build` in `../frontend`
     before the Python steps — unverified against current Render docs since
     the authoring sandbox has no network. If the build fails on `npm`,
     install Node explicitly (e.g. via nvm) in the build command.
   Both items are unverified for the same reason: no network in the sandbox
   this repo was authored in.
3. Apply. First build of `erp-api` runs, in order:
   `npm install && next build (frontend, output: 'export') → pip install →
   collectstatic`. Then, before traffic moves to the new version, the
   `preDeployCommand` runs `migrate → seed_roles` with the runtime
   environment. Migrations deliberately do not run in `buildCommand`: the
   build container has no `DATABASE_URL`, so `migrate` there would only
   touch a throwaway SQLite file while the production schema stays stale.
   **After changing `render.yaml`, sync the Blueprint in the Render
   dashboard** — existing services do not pick up YAML changes on their own.
4. Nothing else to wire up — `frontend/.env.production` fixes
   `NEXT_PUBLIC_API_BASE_URL=/api` (relative, same-origin), which `next build`
   loads automatically. Keep it relative: an absolute host would break the
   moment the page is loaded from a different hostname than the one baked in
   (e.g. `127.0.0.1` vs `localhost` vs the real domain are different origins
   to the browser, even pointing at the same server).

## Post-deploy setup

Roles are seeded automatically by the build. Create the first platform admin
from the `erp-api` shell (Render → erp-api → Shell):

```bash
python manage.py createsuperuser
```

Then create companies/users via Django admin (`/admin/`) or the API. Every new
company automatically gets a `TaxProfile` (Rule #7) and can generate its public
site (M8).

## Smoke test

```bash
curl https://vezano.app/api/health/                   # -> {"status":"ok",...}
curl -sI https://vezano.app/robots.txt | head -1      # -> 200, and /sitemap.xml likewise
# Log in, then hit an authenticated endpoint (cookies set by /api/auth/login/).
```

Open `https://vezano.app/` — same origin serves the frontend, which
pings `/api/health/` and shows whether the API is reachable.

## Environment variables

`erp-api` (see `backend/.env.example` for the full list):
`DJANGO_SECRET_KEY` (auto-generated), `DEBUG=False`, `DJANGO_ALLOWED_HOSTS`,
`DATABASE_URL` (from erp-db), `CELERY_BROKER_URL` (from erp-cache),
`AUTH_COOKIE_SAMESITE`, `MEDIA_ROOT=/var/data/media/`, `LOG_LEVEL`. Python is pinned via `PYTHON_VERSION`;
Node (used only to build the frontend) via `NODE_VERSION`. `CORS_ALLOWED_ORIGINS`
is no longer needed in production — the frontend is same-origin — but stays
useful for local dev against `next dev` on `:3000`.

## Security posture (M10)

With `DEBUG=False` (all deploys), the API enforces: SSL redirect, 1-year HSTS
(subdomains + preload), secure session/CSRF cookies, `X-Frame-Options: DENY`,
content-type nosniff, JWT-in-HttpOnly-cookie auth with refresh-token rotation,
a login throttle, and a min-length-10 password policy.

## Rollback

Render keeps prior deploys per service — use **Rollback** on the service's
Deploys tab. Database migrations are additive across milestones; a code
rollback that predates a migration may require restoring the database from a
Render backup. Take a manual backup (`POST /api/ops/backups/`) before risky
changes.

## Runtime facts worth knowing

- **Shared cache without Redis.** `CACHES` is Django's `DatabaseCache` on the
  table `vezano_cache`, created by migration `core.0004` (so every path that
  runs `migrate` has it). Login throttling and attention badges are therefore
  consistent across gunicorn workers. Tests use an in-memory cache.
- **Connection reuse.** `CONN_MAX_AGE` defaults to 60 s on PostgreSQL (env
  `CONN_MAX_AGE` overrides) with `CONN_HEALTH_CHECKS` on. SQLite never pools.
- **Business time zone.** `Company.timezone` (default `Africa/Khartoum`,
  editable under Settings → Company) decides what "today" means for the
  dashboard, overdue and expiry checks and report day boundaries. The server
  clock and all stored timestamps stay UTC.

## Known caveats

- **Backup retention.** `POST /api/ops/backups/` and the nightly cron generate
  and record logical backups. For durable, off-box retention (Render's
  filesystem is ephemeral), set the object-storage env vars on `erp-api` and
  `erp-backup-cron`: `BACKUP_S3_BUCKET` (required to enable), plus
  `BACKUP_S3_ENDPOINT_URL` (for R2/MinIO), `BACKUP_S3_REGION`,
  `BACKUP_S3_ACCESS_KEY_ID`, and `BACKUP_S3_SECRET_ACCESS_KEY`. When set, each
  backup payload is uploaded and its object key stored on the `BackupRecord`
  (`storage_key`). When unset, backups remain metadata-only (previous
  behavior). `boto3` is bundled but only imported when storage is enabled.
- **Tests run in CI, not in the build sandbox.** The build environment used to
  author this repo had no network to install Django, so the full test suite is
  verified by GitHub Actions on push (lint, system check, migration-sync check,
  deploy check, pytest) rather than locally.

## What is actually deployed today

Two services exist in the dashboard: the web service (`erp-plaform`, i.e.
`erp-api` in this file) and the PostgreSQL database. The Celery worker, the
Key Value store and the backup cron in `render.yaml` were never created.
Nothing in the product needs a worker at request time, so the cheapest
correct setup is the web service plus two **Cron Jobs**:

| Cron Job | Schedule | Start command |
|---|---|---|
| `erp-backup-cron` | `0 2 * * *` | `python manage.py run_scheduled_backup` |
| `erp-daily-scans` | `30 3 * * *` | `python manage.py run_daily_scans` |

Both: same repo/branch, Root Directory `backend`, Build
`pip install -r requirements.txt`, and the same environment variables as
the web service (`DJANGO_SETTINGS_MODULE`, `DJANGO_SECRET_KEY`, `DEBUG`,
`DATABASE_URL`, `SUBSCRIPTION_POLICY`, `PYTHON_VERSION`). Do **not** run a
Celery worker with embedded beat at the same time as `erp-daily-scans`.

## Services created by hand (no Blueprint link)

If the services were created from the dashboard rather than from this
Blueprint, `render.yaml` is documentation only: Render never reads it again.
Every change here must be copied into the service's **Settings** /
**Environment** by hand. The values that have bitten before:

| Service | Setting | Value |
|---|---|---|
| `erp-api` | Pre-Deploy Command | `python manage.py migrate --noinput && python manage.py seed_roles` |
| `erp-api`, `erp-worker`, `erp-backup-cron` | `SUBSCRIPTION_POLICY` | `observe` (then `enforce`) |
| `erp-daily-scans` (optional) | `ACTIVITY_LOG_RETENTION_DAYS` | default `365`; audit rows older than this move nightly from the hot `ActivityLog` table to `ActivityLogArchive` (floor 30 days). The trail is never discarded |
| `erp-worker` (only if deployed) | Start Command | `celery -A config worker -B --loglevel=info --pool=solo` |
| `erp-worker` (only if deployed) | `CELERY_BROKER_URL` | the **Internal Redis URL** of `erp-cache` |
| all Python services | `PYTHON_VERSION` | `3.12.3` (what CI tests) — REQUIRED on the hand-created services; unset, Render picks the newest Python |
| all Python services | `DJANGO_SECRET_KEY` | one shared random value, 50+ chars — REQUIRED; since #57 the app refuses to start without it when `DEBUG=False` |
| `erp-api` | `WEB_CONCURRENCY` | `3` |

A worker log showing `transport: redis://localhost:6379/0` means
`CELERY_BROKER_URL` is missing; `concurrency: 8 (prefork)` followed by
`Out of memory` means the start command lacks `--pool=solo`.

## If a deploy silently never goes live

Render keeps the source checkout between builds. If a build fails, the
previous release stays live and nothing on the site changes — the only
sign is `/sw.js` still reporting the old `BUILD` id. Check the deploy's
build log in the dashboard first; the build command now starts with
`rm -rf node_modules` and uses `npm ci`, so a stale or corrupt dependency
tree cannot be the cause. "Clear build cache & deploy" (Manual Deploy
menu) is the reset for anything else that survives between builds. The
same build command must be copied by hand onto the hand-created
`erp-api` service; `render.yaml` is only the reference.
