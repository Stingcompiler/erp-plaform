# Enhancement: Durable Off-Site Backup Storage (S3/R2)

Status: **built, in review.** Closes the most prominent production gap — backups
were previously metadata-only because Render's filesystem is ephemeral.

## What was built

An **optional, guarded** object-storage backend (`ops/storage.py`) that uploads
backup payloads to any S3/R2-compatible bucket:
- **Activated only when configured** — if `BACKUP_S3_BUCKET` is unset, every
  storage function is a safe no-op and behavior is exactly as before.
- **`boto3` is imported lazily** inside `_client()`, so the dependency is only
  needed when storage is actually enabled (and tests never import it).
- **Fails soft** — a storage error is logged and returns `None`; it never breaks
  the backup audit record.

Wired in:
- `BackupRecord` gained a `storage_key` field (additive `ops/0002` migration).
- The manual backup endpoint and the nightly `run_scheduled_backup` command
  upload the payload and record the object key.
- The backup list response and the Settings backups panel surface the key (an
  **"off-site"** badge when a backup was pushed to storage).

Config (env, set by the operator — never in code): `BACKUP_S3_BUCKET`,
`BACKUP_S3_ENDPOINT_URL` (R2/MinIO), `BACKUP_S3_REGION`,
`BACKUP_S3_ACCESS_KEY_ID`, `BACKUP_S3_SECRET_ACCESS_KEY`. Documented in
`DEPLOYMENT.md` and `.env.example`; `boto3` added to `requirements.txt`.

## Acceptance criteria

| Criterion | Result |
|---|---|
| Storage is off by default (metadata-only) | **Covered** — `is_enabled()` false with no bucket; a manual backup has empty `storage_key`. |
| When enabled, payloads are uploaded and the key recorded | **Covered** — `test_upload_uses_client_when_enabled` and `test_backup_records_storage_key_when_enabled` (mocked client, no network). |
| Storage failures degrade gracefully | **Covered** — a raising client yields `None`; the backup still succeeds. |
| Object key shape is scoped and timestamped | **Covered** — `backups/<company>/<ts>-<kind>.json`. |

## Verifications actually run here

- All backend `.py` incl. the `ops/0002` migration compile; lint +
  unused-import checks clean; repo audit passes. Frontend passes `tsc`.
- Storage logic is unit-tested **without network or boto3** by monkeypatching
  `ops.storage._client`, so the code path is genuinely exercised here; the real
  boto3/S3 call only runs on a configured deploy.

## Deliberately left out

- **Restore-from-object-storage** (download a stored payload by key and restore
  it) — the upload half is done; the download/restore-by-key half remains.
- **Retention/lifecycle policy** (pruning old objects) — left to bucket
  lifecycle rules.
- **Server-side encryption / KMS** knobs — rely on bucket defaults for now.

## Known caveat

- The **live S3/R2 round-trip** can't be exercised in this sandbox (no network).
  The logic is verified with a mocked client; the real call runs on a deploy
  where `BACKUP_S3_*` is set.
