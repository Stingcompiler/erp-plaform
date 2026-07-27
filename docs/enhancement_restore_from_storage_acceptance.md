# Enhancement: Restore From Object Storage

Status: **built, in review.** Completes the durable-backup story — a payload
pushed to S3/R2 can now be pulled back and restored by key.

## What was built

- **`ops.storage.download_backup(key)`** — the mirror of `upload_backup`:
  fetches a stored JSON payload by key (guarded, lazy `boto3`, fails soft to
  `None`, never raises).
- **`POST /api/ops/backups/restore/`** now accepts **either** an inline
  `{"data": <dump>}` **or** `{"storage_key": "<key>"}`. When given a key (and
  storage is enabled), it downloads the payload, parses it, and restores into
  the caller's empty company — same guard as before (refuses a populated
  company). Clear 400s for a missing/unreadable object or malformed JSON.

No new model or migration — this builds on the `storage_key` added in the
previous slice.

## Acceptance criteria

| Criterion | Result |
|---|---|
| A stored payload can be downloaded by key | **Covered** — `test_download_returns_stored_payload` (mocked client). |
| Download is a no-op when storage is disabled | **Covered** — returns `None`. |
| Restore works from a `storage_key` end to end | **Covered** — `test_restore_from_storage_key_into_empty_company`: back up source → restore into a fresh company by key → product reappears. |
| Bad/absent object is rejected cleanly | **Covered** — download returns `None` → 400 (via the view's guards). |

## Verifications actually run here

- Touched files compile; lint + unused-import checks clean; repo audit passes;
  no new migration. The full round trip (upload → download → restore) is
  exercised with a mocked S3 client — **no network or boto3 needed here**; the
  real calls run on a configured deploy.

## Deliberately left out

- A **frontend restore flow** — restore targets an *empty* company (a DR
  operation), so it stays API-driven rather than a button on a populated
  workspace's Settings page.
- **Listing** stored objects from the bucket (the `BackupRecord.storage_key`
  audit rows already record what was written).
- Retention/lifecycle pruning (left to bucket lifecycle rules).

## Known caveat

- The **live S3/R2 round-trip** isn't exercised in this sandbox (no network);
  verified with a mocked client, real on deploy.
