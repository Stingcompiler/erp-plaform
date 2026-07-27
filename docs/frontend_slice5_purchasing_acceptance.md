# Frontend — Slice 5: Purchasing module

Status: **built, in review.**

## What was built

The inbound counterpart to sales. **Field names were verified against the actual
`purchasing/serializers.py`** before building, so the write payloads are exact,
not guessed.

**Suppliers tab.** List with AP balance (`ap_balance`) and active status; a
create-supplier drawer (`name`, `phone`, `email`, `address`) posting to
`/api/suppliers/`.

**Receive stock tab (`ReceivingTerminal`).** The inbound mirror of the POS:
debounced product search into line items with editable **quantity** and **unit
cost** (defaulting to the product's cost), a supplier + warehouse + note, and an
idempotent **`client_uuid`** held stable across retries. Posts to
`/api/receivings/` with `{supplier, warehouse, note, client_uuid, lines:[{product,
quantity, unit_cost}]}` — each line posts one `purchase_in` movement to the M2
ledger. Success confirmation, then reset with a fresh key.

**Bills tab (`BillList`).** Lists bills with total, amount due (`amount_due`),
and status badge; supplier names resolved from the suppliers list. A **cash
payment** drawer posts to `/api/supplier-payments/` (`method: "cash"`, no bank
details — matching the serializer's cash rule).

RBAC-gated: `purchasing` write shows New supplier / Receive / Pay; read-only
roles see suppliers + bills.

## Verifications actually run here

- All frontend JSX/JS pass a `tsc` syntax check (no TS1xxx/TS17xxx).
- Payloads cross-checked against the real serializers: `GoodsReceiptWriteSerializer`
  (supplier/warehouse/note/client_uuid/lines[product,quantity,unit_cost]),
  `SupplierSerializer`, `BillSerializer` (amount_due/status),
  `SupplierPaymentSerializer` (cash requires no bank/reference).

## Deliberately deferred (next slices)

- **Bank-transfer supplier payments** — the serializer needs a company bank
  account, whose endpoint isn't currently exposed; cash-only for now.
- **Purchase orders** UI (the `/purchase-orders/` API exists) and receiving
  against a PO.
- **Batch/lot + expiry** entry on receiving lines (the API accepts
  `lot_number`/`expiry_date`; the UI keeps lines simple for now).
- **Returns, Users, Website, Settings** module screens.

## Known caveat (same as the rest)

- **Not built/run live here** — `next build`/`next lint` need `npm install`
  (network), so they run in CI. JSX verified with `tsc`.

## Next

Returns, Users, Website, or Settings — or wire a deferred backend item.
