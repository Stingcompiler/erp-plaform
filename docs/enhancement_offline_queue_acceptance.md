# Enhancement: Offline Queue UI (M7 sync)

Status: **built, in review.** Surfaces the offline-first sync backend (M7) in the
UI — sales made without connectivity are buffered locally and drained when the
connection returns.

## What was built

- **`lib/syncQueue.js`** — a `localStorage`-backed queue of operations shaped
  like sync API ops (`{ op_type, client_uuid, payload }`), persisted across
  reloads (SSR-safe; degrades quietly if storage is unavailable). This is a
  self-hosted app, so `localStorage` is the appropriate offline store.
- **`SyncProvider`** — context exposing `online`, `pending`, `flushing`,
  `enqueue()`, and `flush()`. Listens to browser `online`/`offline` events and
  **auto-drains** the backlog when connectivity returns. `flush()` batches all
  queued ops into one `POST /api/sync/push/` (with a batch UUID) and clears them
  on a 200/201 — the batch idempotency means a retry is always safe.
- **`SyncStatus`** indicator in the Topbar: "Synced" when clear, "Offline · N"
  when disconnected, and a "Sync N" button (spinner while flushing) to drain
  manually.
- **POS wired for real offline use:** if the browser is offline — or a checkout
  hits a network error while nominally online — the sale is enqueued with its
  existing `client_uuid` (keeping it idempotent) and the cashier sees "Saved
  offline — will sync." No sale is lost.

Mounted in `app/(app)/layout.jsx` inside the toast provider, so it's available
across the app.

## Why this is safe end to end

The queued `pos_checkout` payload is exactly what `POSCheckoutSerializer`
accepts, and the drain path is the same `sync-push` endpoint the integration
test (`test_sync_e2e`) already exercises for applied/duplicate/replay — so a
drained offline sale posts identically to an online one, and re-draining can't
double-post.

## Verifications actually run here

- All frontend JSX/JS pass a `tsc` syntax check (no TS1xxx/TS17xxx).
- Op/batch shapes match the M7 sync contract; the POS payload matches the POS
  serializer.

## Deliberately left out

- **Queuing receiving/returns** offline (POS is wired as the pattern; the same
  `enqueue()` works for other ops whose `op_type` is in the server registry).
- A **detailed queue viewer** (per-op list with retry/discard) — the Topbar
  shows the count and a manual flush for now.
- **Conflict surfacing** if the server rejects a drained op (it stays applied or
  is reported in the push summary; per-op error UI is a follow-up).

## Known caveat (same as everywhere)

- **Not built/run live here** — `next build`/`next lint` need `npm install`
  (network), so they run in CI. JSX verified with `tsc`.
