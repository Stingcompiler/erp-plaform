# M7 — Offline Sync Engine

Status: **built, in review.**

## What was built (`sync` app)

**Batch push (`POST /api/sync/push/`).** A client drains its offline queue by
posting `{batch_uuid, device_id, operations: [{op_type, client_uuid, payload}]}`.
Each operation is dispatched through the **same serializer the live endpoint
uses** (one code path for "make a sale", online or synced) via a registry
covering stock movements/adjustments/transfers, POS checkout, customer &
supplier payments, goods receipts, sales/purchase returns, and credit/debit
notes. Every op is:
- **RBAC-checked** per its module (M6) — an op the role can't perform comes back
  as an error, not a silent apply;
- **idempotent** — if its `client_uuid` already produced a record it's reported
  `duplicate`, never re-applied;
- **isolated in a savepoint** — one bad op reports an error while the rest of the
  batch still commits.

Idempotency is enforced at two levels: the whole batch (`batch_uuid`) and each
op (`client_uuid`). Each push is recorded durably as `SyncBatch` +
`SyncOperation` rows (append-only), so the response is reproducible on replay.

**Delta pull (`GET /api/sync/pull/?since=<iso>`).** Returns records changed
since a cursor for the entities the role may read (products, stock movements,
customers, invoices, suppliers), plus a fresh `cursor` for the next pull.

## Acceptance criteria

| Criterion | Result |
|---|---|
| A queued batch applies each operation exactly once after reconnect | **Covered by tests** — `BatchApplyTests`: a 2-op batch applies both; one movement + one invoice created. |
| Re-submitting the same work is a no-op (idempotent) | **Covered by tests** — replaying the whole `batch_uuid` returns stored results with no new rows; the same op `client_uuid` in a new batch reports `duplicate`. |
| Each operation reports its outcome; partial failures don't corrupt the batch | **Covered by tests** — `test_partial_failure_isolated`: a bad op errors while the good op still commits; per-op statuses returned. |
| Role gates carry into sync | **Covered by tests** — `SyncRBACTests`: an Inventory Officer's POS-checkout op is rejected. |
| Delta pull returns changes since a cursor | **Covered by tests** — `SyncPullTests`. |

## Design notes

- **Reuse, not reimplementation.** The offline path and the online path share
  serializers, so business rules (sign validation, gapless numbering, Rule #5
  quarantine, manual-payment rules) apply identically to synced operations.
- **Common offline flow is atomic.** A POS sale + its payment is a single
  `pos_checkout` op (payment nested), so it needs no cross-operation reference.

## Deliberately deferred / left out

- **Intra-batch temp-ID resolution.** An op that references another op created
  in the *same* batch (e.g. a standalone payment against an invoice created
  moments earlier in the same push) isn't auto-linked — clients either bundle
  them (as POS checkout does) or sync the invoice first. Client-temp-ID mapping
  is a future enhancement.
- **Field-level merge/conflict resolution.** Our records are append-only, so
  "conflicts" reduce to duplicates (handled) and ordering; there is no
  last-writer-wins field merging to do.
- **Pull pagination beyond a 500-row cap** and per-entity cursors — the pull is
  a single timestamp cursor with a hard cap for now.

## Verifications actually run here

- All backend `.py` incl. the 2-model sync migration compile; lint +
  unused-import checks clean.

## Known caveats (unchanged)

- **Tests not executed live** — no network to install Django; suite written +
  syntax-verified, runs in CI, with the `makemigrations --check` gate.

## Next

M8 — Public Website / Landing Page Generator. Not started this session. Say
"continue".
