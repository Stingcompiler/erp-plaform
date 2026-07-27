# Enhancement: Bank-Transfer Payments (frontend)

Status: **built, in review.** Closes the "cash-only" limitation left in the POS
(slice 3) and supplier-payment (slice 5) flows.

## What was built

The backend already exposed `/api/bank-accounts/` (CompanyBankAccountViewSet,
`sales` module) and both payment serializers already accepted bank transfers —
the gap was purely UI. This slice wires it through:

- **POS checkout** — a **Bank transfer** method now reveals a receiving
  **bank-account** selector and a **reference (last 4)** field, sent as
  `payment.company_bank_account` + `payment.reference_last4` (matching
  `POSPaymentSerializer`).
- **Supplier bill payment** — the drawer gained a method selector; **Bank
  transfer** reveals a **from-account** selector and reference, sent as
  `from_bank_account` + `reference_last4` (matching `SupplierPaymentSerializer`).
- **Bank accounts manager** — a new **Bank accounts** tab on the Sales page
  (gated by `sales` write, matching the endpoint's RBAC) to list and add
  company receiving accounts. Accounts are fetched into both the POS and the
  bill-payment drawer so the selectors are populated.

## Verifications actually run here

- All frontend JSX/JS pass a `tsc` syntax check (no TS1xxx/TS17xxx).
- Payloads cross-checked against the real serializers: POS payment
  (`method`, `company_bank_account`, `reference_last4`, `amount`) and supplier
  payment (`method`, `from_bank_account`, `reference_last4`, `amount`,
  `client_uuid`); bank account create matches `CompanyBankAccountSerializer`
  (`bank_name`, `account_name`, `account_number`).
- No backend change; backend audit unaffected.

## Deliberately left out

- Payment **verification** UI (the payment models have a verify action/fields;
  recording is wired, verification workflow is not).
- Editing/deactivating existing bank accounts (create + list for now).
- Customer (AR) bank-transfer receipts outside the POS.

## Known caveat (same as everywhere)

- **Not built/run live here** — `next build`/`next lint` need `npm install`
  (network), so they run in CI. JSX verified with `tsc`.
