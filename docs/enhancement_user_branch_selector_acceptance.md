# Enhancement: Branch Selector on the User Form

Status: **built, in review.** The UI counterpart to backend branch-level
visibility — a user's branch can now be assigned from the app, not just the API.

## What was built

- **User form** gained a **Branch** selector (populated from `/api/branches/`),
  with a "No branch (company-wide)" default and a hint that branch-scoped roles
  see only that branch's records. `branch` is included in both create and update
  payloads (matching the writable `branch` field on `UserSerializer`).
- **Users list** gained a **Branch** column showing each user's assigned branch
  (resolved from the branches list), so assignments are visible at a glance.
- `lib/api.js`: added `users.branches()`; the Users page fetches branches
  (gracefully empty if the role can't read them) and threads them to the form.

Together with the backend work, an admin can now assign a branch to a
branch-scoped user and have that user's Warehouse/Invoice/SalesOrder/Quotation/
PurchaseOrder views filter to their branch.

## Verifications actually run here

- All frontend JSX/JS pass a `tsc` syntax check (no TS1xxx/TS17xxx).
- Payload matches the serializer: `branch` writable, sent as an id or `null`.
- Table `colSpan`s updated for the added column.

## Deliberately left out

- **Filtering the branch list by the selected role's scope** (all active
  branches are shown; assigning a branch to a business/platform role is simply
  inert on the backend).
- Creating/editing **branches** themselves from the UI (the `/api/branches/`
  CRUD exists; no management screen yet — could live under Settings).

## Known caveat (same as everywhere)

- **Not built/run live here** — `next build`/`next lint` need `npm install`
  (network), so they run in CI. JSX verified with `tsc`.
