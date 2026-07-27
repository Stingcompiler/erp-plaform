# M10 — Backup/Restore, Multi-language, Theme, Security Hardening

Status: **built, in review.**

## What was built

### Backup / Restore (`ops` app)
- `dump_company()` produces a live JSON snapshot of a company's master and
  transactional data (nothing stored to drift). `BackupRecord` audits every
  backup and restore (Rule #8), append-only.
- `POST /api/ops/backups/` creates a backup + returns the snapshot;
  `GET /api/ops/backups/` lists records. Gated to the `settings` module
  (Business Owner / platform admin).
- `POST /api/ops/backups/restore/` restores **master** data from a dump into
  the caller's company, and **refuses if the company already has products** so
  a restore can never clobber live data.
- The M0 `run_scheduled_backup` cron stub is now a **real** command that backs
  up every active company nightly and records the result.

### Multi-language + Theme (`ops` app)
- `UserPreference` (per user): `language` (en/ar) and `theme`
  (light/dark/system); `direction` is derived (`ar` → `rtl`).
- `GET/PATCH /api/ops/preferences/` and `GET /api/ops/languages/`.
- Django `LocaleMiddleware` + `LANGUAGES = [en, ar]` wired for backend i18n.

### Security hardening (settings + auth)
- **Password policy** enforced on the API (`UserSerializer` runs Django's
  validators; minimum length raised to 10).
- **Refresh-token rotation** on (`ROTATE_REFRESH_TOKENS`, blacklist after
  rotation).
- **Login throttling** — a scoped 10/min rate on the login endpoint.
- **Security headers** always on (nosniff, `X-Frame-Options: DENY`,
  referrer-policy, proxy-SSL header for Render); and in production: SSL
  redirect, 1-year HSTS with subdomains + preload, secure session/CSRF cookies.

## Acceptance criteria

| Criterion | Result |
|---|---|
| A backup can be created and is logged | **Covered** — `BackupRestoreTests`: backup returns a snapshot containing the product; a `manual` `BackupRecord` is written; list works. |
| A backup can be restored; restore is guarded and logged | **Covered** — restore into an empty company recreates the product; restoring into a non-empty company is rejected (400). |
| Scheduled backup runs for all companies | **Covered** — `run_scheduled_backup` writes a `scheduled` success record. |
| Language/theme preferences persist; Arabic implies RTL | **Covered** — `PreferenceTests`: defaults en/system/ltr; setting `ar` returns `rtl`; invalid language rejected; languages list. |
| Security hardening applied | **Covered** — API rejects a weak password and accepts a strong one; rotation + security-header settings asserted. |

## Verifications actually run here

- All backend `.py` incl. the 2-model `ops` migration compile; lint +
  unused-import checks clean; 11 apps registered.
- Added `conftest.py` clearing the cache before each test so the new login
  throttle can't bleed state across tests.

## Deliberately deferred / left out

- **Durable backup storage.** Snapshots are generated and their size/record
  count recorded, but pushing the payload to object storage (S3/R2) isn't
  wired — Render's filesystem is ephemeral, so this is intentionally an infra
  step (M12 / ops config), not local-disk retention.
- **Transactional restore.** The dump captures invoices/payments/movements, but
  restore replays only master data (parent-category hierarchy also flattened);
  full relational re-import with ID remapping is a larger effort.
- **Actual translation catalogs (.po/.mo).** The backend exposes languages and
  stores the preference; UI string translation lives in the frontend.
- **Per-request cache backend for throttling.** Login throttle uses the default
  in-process cache (per worker); a shared Redis cache would make the limit
  global — a small config change later.

## Known caveats (unchanged)

- **Tests not executed live** — no network to install Django; suite written +
  syntax-verified, runs in CI with the `makemigrations --check` gate.

## Next

M11 — Pluggable Tax / E-invoicing scaffold. Not started this session. Say
"continue".
