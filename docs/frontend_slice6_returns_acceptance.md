# Frontend — Slice 6: Returns module

Status: **built, in review.**

## What was built

The Returns screen, surfacing the distinctive **Rule #5 quarantine → disposition**
flow. Contracts were read from `returns/serializers.py` and `returns/views.py`
first, so the create payload and the disposition action are exact.

**Returns list (`/returns`).** Sales returns with reason, line count, and a
status badge — **"N quarantined"** (warn) until every line is dispositioned,
then **"Dispositioned"** (ok).

**New return (`NewReturnDrawer`).** Pick the invoice, add returned items via
product search + quantity, add a reason. Posts to `/api/sales-returns/` with an
idempotent `client_uuid` and `lines:[{product, quantity}]`. The drawer states
plainly that returned items are quarantined and don't re-enter sellable stock
until dispositioned.

**Disposition (`DispositionDrawer`).** The Rule #5 highlight: each quarantined
line gets a **Restock** (to a chosen or the invoice's warehouse) or **Scrap**
decision; submitting posts `{decisions:[{line_id, action, warehouse?}]}` to
`/api/sales-returns/<id>/disposition/`. Restock is the *only* path that posts a
`sales_return_in` movement back into sellable inventory; scrap writes off with no
stock added. Already-settled lines are shown read-only with their outcome.

RBAC-gated: `returns` write shows New return / Disposition; read-only roles see
the list.

## Verifications actually run here

- All frontend JSX/JS pass a `tsc` syntax check (no TS1xxx/TS17xxx).
- Payloads cross-checked against `SalesReturnWriteSerializer`
  (`invoice`, `reason`, `client_uuid`, `lines[product, quantity]`) and the
  `disposition` action (`decisions[line_id, action:"restock"|"scrap",
  warehouse?]`), plus the `quarantine/restocked/scrapped` disposition values.

## Deliberately deferred (next slices)

- **Purchase returns** UI (the `/purchase-returns/` API exists; it posts the
  outbound movement immediately, so it needs a different, simpler form).
- **Credit / debit notes** screens (APIs exist).
- Returning against specific **invoice lines** (the API accepts `invoice_line`;
  the UI currently returns by product).
- **Users, Website, Settings** module screens.

## Known caveat (same as the rest)

- **Not built/run live here** — `next build`/`next lint` need `npm install`
  (network), so they run in CI. JSX verified with `tsc`.

## Next

Users, Website, or Settings — or a deferred backend item.
