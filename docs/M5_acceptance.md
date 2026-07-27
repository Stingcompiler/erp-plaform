# M5 — Returns & Credit Notes

Status: **built, in review.**

## What was built (`returns` app)

**Sales returns with quarantine/disposition — the Rule #5 centerpiece.**
`SalesReturn` + `SalesReturnLine` record a customer return against an invoice.
Creating the return posts **no stock movement at all** — every line starts in
`quarantine`. Returned goods only re-enter sellable inventory through a
deliberate `POST /api/sales-returns/{id}/disposition/` call:
- `restock` posts a `sales_return_in` movement into a chosen sellable warehouse
  and marks the line `restocked`;
- `scrap` marks it `scrapped` and adds nothing back.
A line can be dispositioned only once. This guarantees returned stock never
silently re-enters sellable inventory.

**Purchase returns.** `PurchaseReturn` + lines. Because goods physically leave
us, each line immediately posts a `purchase_return_out` (−qty) movement — no
quarantine needed.

**Credit & debit notes.** `CreditNote` reduces customer AR; `DebitNote` reduces
supplier AP. Both append-only. They feed the balances via two small, additive
extensions to earlier computed methods (see cross-milestone note below).

All returns/notes are company-scoped (Rule #1), append-only (Rule #9), audit
logged (Rule #8), and idempotent via `client_uuid` (Rule #2).

## Acceptance criteria

| Criterion | Result |
|---|---|
| Returned stock never silently re-enters sellable inventory | **Covered by tests** — `Rule5QuarantineTests`: creating a return posts zero `sales_return_in` movements and leaves sellable on-hand unchanged; only `restock` disposition adds stock; `scrap` adds none; double-disposition rejected. |
| Credit notes reduce what the customer owes | **Covered by tests** — `CreditNoteARTests`: a 50 credit drops a 200 invoice's `amount_due` to 150. |
| Purchase returns reduce our stock; debit notes reduce AP | **Covered by tests** — `PurchaseReturnTests`, `DebitNoteAPTests`. |

## Cross-milestone touches (flagged for review)

Two earlier **computed methods** were extended — no schema change to any M3/M4
table, purely additive:
- `sales.Invoice.amount_due()` now subtracts non-void credit notes.
- `purchasing.Supplier.ap_balance()` now subtracts non-void debit notes.

Both use a lazy import of `returns.models` to avoid an import cycle. Existing
M3/M4 tests are unaffected (the subtracted total is 0 when no notes exist).
Raising this explicitly because it modifies financial calculations introduced
in prior milestones, even though it doesn't reshape their tables.

## Verifications actually run here

- All backend `.py` incl. the 6-model returns migration compile.
- Lint clean (fixed one long line + one unused local); unused-import check
  clean across the returns app and the two edited model files.

## Deliberately deferred / left out

- **Return quantity ≤ invoiced quantity** enforcement (over-return guard) —
  not validated yet; a manager currently controls what's accepted.
- **Auto-linking credit-note amounts to specific return lines / partial credit
  math** — credit amount is entered explicitly.
- **Restock-to-original-batch** — restock goes to a warehouse, not back into
  the exact source batch.

## Known caveats (unchanged)

- **Tests not executed live** — no network to install Django; suite written +
  syntax-verified, runs in CI.
- **Migrations hand-authored**, gated by `makemigrations --check` in CI.

## Next

M6 — Role-Based Visibility & Dashboards (per-role access enforcement). Not
started this session. Say "continue".
