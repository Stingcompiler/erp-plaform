# Handoff — where the work stands (2026-09-14, after PR #13)

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

Then phase D (upgrade n→n+1 **with a real migration**, rollback via the
`current` symlink after restoring the pre-upgrade backup) and phase E
(Arabic customer guide, ship/never-ship checklist, contract terms: perpetual
+ annual maintenance; term → grace → read-only, no data loss).

## Operator reminders

- Every `render.yaml` change must be copied into the Render dashboard by hand.
- Move `SUBSCRIPTION_POLICY` to `enforce` after a few days of clean
  `subscription_observe` / `subscription_capacity_observe` log lines.
- Never run `npm run build` while `next dev` is up (it clobbers `.next`).

## To resume in a new chat

> واصل خطة النسخة المستقلة — المرحلة C على VPS حقيقي، أو المرحلة D

Add the VPS address and SSH access in the same message if one exists.
