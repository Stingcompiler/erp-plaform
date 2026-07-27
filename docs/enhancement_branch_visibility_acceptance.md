# Enhancement: Branch-Level Row Visibility

Status: **built, in review.** Closes the row-level access gap flagged since M6
(which enforced *module* access but not per-branch *row* filtering).

## What was built

Opt-in branch scoping in the shared `CompanyScopedQuerySetMixin`
(`core/scoping.py`), layered on top of the existing company isolation:

- A viewset sets `branch_field = "branch"` to enable it. When set, a user whose
  **role is branch-scoped AND who has a branch assigned** sees only rows for
  their branch **plus** shared (null-branch) rows — other branches' rows are
  hidden from list *and* detail (a cross-branch id yields 404). Their newly
  created rows are automatically tagged with their branch.
- **Purely additive / safe:** users without a branch assigned, and
  business/platform users, are unaffected. Existing tests (whose branch-scoped
  users have no branch) see no change.

Opted-in viewsets — the branch-bearing models: **Warehouse**, **Invoice**,
**SalesOrder**, **Quotation**, **PurchaseOrder**. Any other branch-bearing
viewset enables the same behavior with a one-line `branch_field` attribute.

## Acceptance criteria

| Criterion | Result |
|---|---|
| Branch user sees only own-branch + shared rows | **Covered** — sees WH A + WH Shared, not WH B. |
| Other branch's row is inaccessible (list & detail) | **Covered** — cross-branch warehouse detail returns 404. |
| Business/platform users see all branches | **Covered**. |
| Branch-scoped user *without* a branch is unaffected | **Covered** — sees all (keeps prior behavior; no test breakage). |
| Created rows tagged with the user's branch | **Covered** — a warehouse created by a Branch A user has `branch = A`. |

## Verifications actually run here

- All backend `.py` compile; lint + unused-import checks clean; repo audit
  passes. **No model change → no migration** (the gate stays green). Because the
  filter only activates for branch-scoped users *with* a branch, and no existing
  test assigns one, prior behavior is preserved.

## Deliberately left out

- **Movement/report branch scoping** via warehouse→branch joins (movements have
  no direct branch FK; they'd scope through `warehouse__branch`). Left as a
  follow-up; the direct-branch models are covered.
- **Customer/Supplier** branch assignment (those models are company-wide here).
- A **branch selector** in the frontend user form (users get a branch via the
  API/admin; the UI form assigns role + active but not branch yet).

## Known caveat (same as everywhere)

- **Not executed live here** — no network to install Django; tests run in CI.
