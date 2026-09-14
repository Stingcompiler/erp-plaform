# Handoff — where the work stands (2026-09-14, main @ be4d6d1)

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

## Next: standalone plan, phase C

Run `deploy/standalone/README.md` + `OPERATIONS.md` **literally on a clean
Ubuntu 24.04 VPS**: PostgreSQL, venv, `npm run build`, `migrate`,
`bootstrap_standalone`, first owner, systemd units, TLS (Caddy or nginx +
certbot), import a licence issued with the phase-A tools, ring a POS sale,
go offline, sync, then `restore.sh` on an empty database. Fix every break in
the scripts themselves. This was never done; it is the real risk.

If no VPS is available yet: dry-run `package_release.sh`, `verify_release`,
`preflight` and `restore.sh` locally against a local PostgreSQL.

Then phase D (signed release tarball, upgrade n→n+1 with a migration,
rollback via the `current` symlink) and phase E (Arabic customer guide,
ship/never-ship checklist, contract terms: perpetual + annual maintenance;
term → grace → read-only, no data loss).

## Operator reminders

- Every `render.yaml` change must be copied into the Render dashboard by hand.
- Move `SUBSCRIPTION_POLICY` to `enforce` after a few days of clean
  `subscription_observe` / `subscription_capacity_observe` log lines.
- Never run `npm run build` while `next dev` is up (it clobbers `.next`).

## To resume in a new chat

> واصل خطة النسخة المستقلة من المرحلة C

Add the VPS address and SSH access in the same message if one exists.
