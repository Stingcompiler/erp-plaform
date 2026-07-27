# Frontend — Slice 3: POS / Sales module

Status: **built, in review.**

## What was built

The point-of-sale flow — the system's most distinctive path, driving the
offline-idempotent `pos_checkout` endpoint.

**POS terminal (`PosTerminal`).** Debounced product search adds lines to a cart
with quantity steppers; warehouse and (optional) customer selectors; a manual
payment method (cash / bank transfer) and amount. **Checkout** posts to
`/api/pos/checkout/` with a `client_uuid` generated once per sale and held
stable across retries — so a network wobble can't double-record a sale. On
success it shows a receipt with the server-authoritative invoice number,
subtotal, tax, and total, then resets with a fresh key. On failure the cart and
key are preserved for a safe retry. Client shows the subtotal only and defers
tax to the server (avoids needing the settings-gated tax profile).

**Invoices tab + receipt drawer (`InvoiceList`).** Lists recent invoices
(number, customer, total, status badge); clicking opens a receipt rendered
through the **M11 tax handler** (`/api/invoices/<id>/document/`) — a formatted
receipt for the `simple` format, or the Gulf VAT XML scaffold for `gulf_vat`.

**Sales page (`/sales`).** Tabs between Point of sale and Invoices, gated by
RBAC: `sales` write shows the POS; read-only roles see only the invoice list;
no `sales` access shows a notice.

No backend changes this slice — it consumes existing M3/M11 endpoints.

## Verifications actually run here

- All frontend JSX/JS pass a `tsc` syntax check (no TS1xxx/TS17xxx).

## Deliberately deferred (next slices)

- **Purchasing, Returns, Reports, Users, Website, Settings** module screens
  (their APIs are live; placeholder routes remain).
- Barcode-scanner input, held/parked sales, and split payments.
- Customer creation from the POS (currently pick existing or walk-in).
- The offline queue UI on the M7 sync endpoints (the `client_uuid` groundwork is
  already in place here).

## Known caveat (same as the rest)

- **Not built/run live here** — `next build`/`next lint` need `npm install`
  (network), so they run in CI. JSX verified with `tsc`. Some response-field
  names (e.g. `customer_name`, `number_display`) are consumed defensively with
  fallbacks; any mismatch surfaces in CI/integration, not as a crash.

## Next

Another module slice (Purchasing or Reports are natural next steps), or wiring
the deferred backend items — say which.
