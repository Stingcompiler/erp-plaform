# Go-live gate: recovery (F16)

**Targets (owner decision 2026-09-20):** RPO ≤ 24 h, RTO ≤ 4 h.
**Rule:** no paying customer until every box below is ticked and the drill
table is filled in with real numbers. This is a shared gate — the code is
merged, the rest is Render/Meta/storage configuration only the owner can do.

## What exists today

| Layer | What it is | Where it lives | Survives |
|---|---|---|---|
| Postgres (`erp-db`) | every transaction | Render managed Postgres | Render's own daily backups (plan-dependent), *not* our cron |
| Nightly logical dumps | per-company JSON via `run_scheduled_backup` (03:00 UTC) | object storage when `BACKUP_S3_*` is set, else a gzip row inside the same database | with storage configured: loss of the database. Without it: **nothing** — the copy dies with the database |
| Media (uploads: proofs, product images, documents) | files | Render persistent disk on `erp-api` | restarts and deploys; *not* disk loss or region loss |

The logical dump restores **one empty company** (`POST /api/ops/backups/restore/`).
It is a tenant-level safety net, not disaster recovery: full recovery is a
**Postgres restore + media restore**, then the fingerprint check below.

## Gate checklist (owner)

- [ ] **A. Managed Postgres backups on.** Render dashboard → `erp-db` → Backups:
      daily backups visible with ≥ 7 days retention. If the plan does not
      include backups, upgrade the database plan — this alone satisfies RPO 24 h
      for the database.
- [ ] **B. Object storage for the logical dumps.** Create a bucket (Cloudflare R2
      or S3), a key pair limited to that bucket, and set on `erp-api` **and**
      `erp-backup-cron`: `BACKUP_S3_BUCKET`, `BACKUP_S3_ENDPOINT_URL`,
      `BACKUP_S3_REGION`, `BACKUP_S3_ACCESS_KEY_ID`, `BACKUP_S3_SECRET_ACCESS_KEY`.
      Trigger the cron once; the newest `BackupRecord` rows must carry a
      `storage_key`. After #146 a failed run turns the cron red — check it is green.
- [ ] **C. Media copy.** Render disks are not backed up by Render. Until uploads
      move to object storage (open follow-up), take a weekly copy:
      `render ssh erp-api` → `tar czf - /var/data/media | …` to your machine, or
      a one-line `rclone sync /var/data/media r2:vezano-media` from the shell.
      Record the date of the last copy in the table below.
- [ ] **D. Secrets on file.** `DJANGO_SECRET_KEY`, `SECRETS_ENCRYPTION_KEY`
      (#148), `WHATSAPP_*`, VAPID keys, SMTP — stored in the owner's password
      manager. A restored database is useless without the same keys.
- [ ] **E. Restore drill done** (below) and its numbers pasted here.

## Restore drill (≈ 1–2 hours; do it once before the first customer, then quarterly)

1. **Fingerprint production.** Render shell on `erp-api`:
   `python manage.py recovery_fingerprint --json > before.json` (also print
   without `--json` and paste it below).
2. **Create a scratch database** in Render (`erp-db-drill`, same plan) and
   restore the latest managed backup into it (Render → Backups → Restore /
   or `pg_restore` from the downloaded dump).
3. **Point a scratch web service at it**: duplicate `erp-api` as `erp-api-drill`
   (or temporarily set `DATABASE_URL` on a preview instance) with the *same*
   `DJANGO_SECRET_KEY` and `SECRETS_ENCRYPTION_KEY`. Run `python manage.py migrate`
   and `python manage.py preflight`.
4. **Fingerprint the restored copy**: `python manage.py recovery_fingerprint --json > after.json`.
   `diff before.json after.json` must be empty except for rows written to
   production after the backup time (note them).
5. **Media**: restore the latest media copy to the drill service's disk; open
   one payment proof and one product image from the UI.
6. **Sign in** as an owner of one company, open POS, dashboard, finance,
   subscription; send a WhatsApp test message (proves the encrypted token
   restored with the key).
7. **Logical-dump path**: from the drill service, `POST /api/ops/backups/restore/`
   with the newest `storage_key` into a new empty company; its product count
   must match the source company's.
8. **Time it.** Start at step 2, stop after step 6. That is your RTO.
9. **Tear down** the drill service and database.

## Drill record

| Date | Backup time (RPO) | Steps 2–6 duration (RTO) | Fingerprint diff | Media copy date | Done by |
|---|---|---|---|---|---|
| | | | | | |

`recovery_fingerprint` output (before / after):

```
(paste here)
```

## Follow-ups (not gating month one)

- Move uploads to object storage so media stops depending on a single disk.
- Point-in-time recovery when a customer's volume justifies the Postgres plan.
