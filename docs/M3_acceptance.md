# M3 — Sales & POS + Manual Payments

Status: **built, in review.**

## What was built (`sales` app)

**Master data:** `Customer` (with derived `ar_balance`, document-level, never
stored) and `CompanyBankAccount` (the company's receiving account for
bank-transfer payments).

**Sales documents:** `Quotation` + lines (with `set_status` and
`convert_to_order` actions) and `SalesOrder` + lines. `Invoice` + `InvoiceLine`
are the financial record — **append-only** (Rule #9), created only via POS
checkout, with status *derived* from payments (`issued` → `partially_paid` →
`paid`) rather than a mutable field. A void is reserved for a Credit Note (M5),
never an in-place edit.

**Gapless invoice numbering:** a per-company `InvoiceSequence` allocated under
`select_for_update` inside the same transaction as the invoice insert, so a
rolled-back sale never burns a number — numbering is sequential and gapless per
company, and independent across companies.

**Manual payments (Rule #3):** `Payment` records method (`cash` /
`bank_transfer`), the receiving `CompanyBankAccount`, the sender's bank name,
and the last-4 reference digits — with **no external API calls anywhere**. Bank
transfers require those details; cash rejects them. `verified_at`/`verified_by`
support later manual reconciliation via a `verify` action and never block a
sale. Payments are append-only (except the designed verify fields).

**POS checkout (`POST /api/pos/checkout/`):** one atomic, **offline-capable,
idempotent** call that creates the invoice + lines, the `sale_out` stock
movements, and an optional payment. Re-sending the same `client_uuid` returns
the existing invoice instead of ringing the sale up twice (Rule #2). Tax is
applied from the company's `TaxProfile` flat rate (Rule #7), snapshotted onto
the invoice. All endpoints inherit M1 company scoping + activity logging.

## Acceptance criteria

| Criterion | Result |
|---|---|
| A sale completes fully offline with cash and syncs cleanly (idempotent) | **Covered by tests** — `OfflineCashSaleTests`: cash checkout returns a paid invoice, deducts exactly one `sale_out` movement; replaying the same `client_uuid` returns the same invoice with no second sale. |
| Bank-transfer payment records bank name + last-4 with no external calls | **Covered by tests** — `ManualPaymentTests`: details stored; missing details / non-digit ref / cash-with-bank-details all rejected. No network is contacted (there is no gateway code). |
| Invoice numbering sequential and gapless per company | **Covered by tests** — `InvoiceNumberingTests`: 1,2,3 within a company; independent per company. Gaplessness on rollback is guaranteed by the atomic + `select_for_update` design. |

## Verifications actually run here

- All backend `.py` incl. the 10-model sales migration compile.
- Lint clean; static unused-import check clean (also refactored the shared
  `AppendOnlyScopedViewSet`/`IdempotentCreateMixin` into `core/scoping.py` so
  inventory and sales share one implementation).

## Deliberately deferred / left out

- **Credit notes / invoice void flow** — M5 (Returns). `Invoice.is_void`
  exists but is only ever set by that flow.
- **Stock-availability enforcement on sale.** Offline-first: a sale is recorded
  even if it drives stock negative; reconciliation is a later concern. No hard
  block by design.
- **Quotation/SalesOrder editing** and cross-company validation of *quotation
  line* products (low-risk draft data). The financial paths (invoice, payment,
  stock, bank account) are fully company-checked.
- **Payment allocation across multiple invoices** — a payment targets one
  invoice; AR is tracked per document.

## Known caveats (unchanged)

- **Tests not executed live** — no network to install Django here; suite
  written + syntax-verified, runs in CI.
- **Migrations hand-authored**, gated by `makemigrations --check` in CI.

## Next

M4 — Purchasing & Suppliers. Not started this session. Say "continue".
