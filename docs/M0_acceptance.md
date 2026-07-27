# M0 — Scaffolding & Environment

Status: **built, in review.**

## What was built

**Backend (`/backend`) — Django 5 + DRF monolith**
- Django project `config/` with `settings.py` (env-driven via django-environ:
  SQLite in dev, `DATABASE_URL` Postgres in prod), `urls.py`, `wsgi.py`
  (Gunicorn target), `asgi.py`, and `celery.py` (the `erp-worker` app).
- `core` app holding the unauthenticated health-check endpoint at
  `GET /api/health/` (reports service + DB reachability, returns 200).
- `run_scheduled_backup` management command as the `erp-backup-cron`
  entry point — a deliberate stub until M10.
- `requirements.txt` pinning Django 5.0.x, DRF, SimpleJWT (ready for M1's
  cookie auth), CORS headers, psycopg 3, Gunicorn, WhiteNoise, Celery,
  Redis, plus pytest/flake8 for CI.
- `pytest.ini`, `.flake8`, `.env.example`.

**Frontend (`/frontend`) — Next.js App Router**
- App Router skeleton (`app/layout.js`, `app/page.js`, `globals.css`) with
  Tailwind, Framer Motion, Lucide, and a credentialed Axios client
  (`withCredentials: true`, ready for M1 HttpOnly-cookie auth).
- Home page pings `/api/health/` and shows live backend reachability.
- Tailwind/PostCSS/ESLint config; `next start` is the production command.
- `.env.example`.

**Infra / repo**
- `render.yaml` Blueprint defining all six services: `erp-api` (Python web,
  Gunicorn, healthCheckPath `/api/health/`), `erp-frontend` (Node web,
  `next start`), `erp-worker` (Python background worker, Celery),
  `erp-backup-cron` (Python cron, daily 02:00 UTC), `erp-db` (managed
  Postgres), `erp-cache` (managed Key Value / Celery broker). No Docker.
- GitHub Actions CI (`.github/workflows/ci.yml`): backend flake8 + pytest,
  frontend lint + build, on every push and PR.
- `PROJECT_RULES.md` at repo root (verbatim), `README.md`, `.gitignore`,
  build plan copied into `docs/`.

## Acceptance criteria

| Criterion | Result |
|---|---|
| No Dockerfile / docker-compose anywhere | **Pass** — `find` for `Dockerfile*` / `docker-compose*` returns nothing. |
| Health-check endpoint returns 200 | **Pass by code + test** — see caveat on live execution below. |
| `render.yaml` valid, all 6 services, correct native runtimes | **Pass** — parses; erp-api/worker/backup-cron = python, erp-frontend = node, plus erp-db + erp-cache. |
| CI runs lint + tests on push | **Pass (config present)** — workflow defined; first real run happens on push to the connected repo. |

## Verifications actually run in this environment

- No Docker artifacts present (`find`).
- `render.yaml` parses as valid YAML; all six services enumerated with
  correct runtimes/types.
- Every backend `.py` compiles (`python -m py_compile`).
- Every frontend `.js` parses (`node --check`).
- Manual lint pass: no lines >100 chars, no trailing whitespace.

## Deliberately deferred / left out

- **JWT-via-HttpOnly-cookie auth** — M1. SimpleJWT is installed and the
  DRF/CORS/Axios config is pre-wired for it, but no auth is active yet.
- **Company-scoping middleware / base queryset mixin (Rule #1)** — M1.
  Placeholder comments mark where it slots into `MIDDLEWARE` and DRF.
- **ActivityLog model + login/logout logging (Rule #8)** — M1.
- **Real backup logic** — M10; `run_scheduled_backup` is a stub.
- **Celery tasks** — none yet; the worker app exists with autodiscover.
- No business models, migrations, or domain apps beyond `core`.

## Known caveats to verify at first deploy

- **Tests were NOT executed live in this build environment** — it has no
  network access, so Django/DRF could not be `pip install`ed to run
  pytest. The suite (`core/tests.py`: health-check 200, health-check
  unauthenticated, backup-cron command runs) is written and all code is
  syntax-verified, but the green run must come from CI on first push.
  This is the one acceptance item proven by code + CI config rather than
  by observed passing output.
- **`render.yaml` schema for the Key Value store and the
  `fromService`/`fromDatabase` property names** were written from
  knowledge, not validated against live Render docs (no network). Confirm
  against current Render Blueprint docs on the first Blueprint deploy.

## Next

M1 — Auth, Users, Roles, Company/Branch/Department. Do not start it in
this session (per PROJECT_RULES working agreement).
