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

## First deploy

1. Push this repo to GitHub.
2. In Render: **New → Blueprint**, select the repo. Render reads `render.yaml`
   and provisions all five components.
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
   collectstatic → migrate → seed_roles`.
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
curl https://erp-api.onrender.com/api/health/        # -> {"status":"ok",...}
# Log in, then hit an authenticated endpoint (cookies set by /api/auth/login/).
```

Open `https://erp-api.onrender.com/` — same origin serves the frontend, which
pings `/api/health/` and shows whether the API is reachable.

## Environment variables

`erp-api` (see `backend/.env.example` for the full list):
`DJANGO_SECRET_KEY` (auto-generated), `DEBUG=False`, `DJANGO_ALLOWED_HOSTS`,
`DATABASE_URL` (from erp-db), `CELERY_BROKER_URL` (from erp-cache),
`AUTH_COOKIE_SAMESITE`, `LOG_LEVEL`. Python is pinned via `PYTHON_VERSION`;
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
