# Enhancement: Branch Management Screen

Status: **built, in review.** Gives the `org` module a real UI, completing the
branch story: create the branches that branch-level visibility and the user
branch selector depend on.

## What was built

- A new **Organization** nav entry (`/org`, `org` module, Building icon) — shown
  only to roles with `org` access (Business Owner / Super Administrator).
- **Branch management screen**: a company-scoped list of branches (name, code,
  phone, active status) with **create** and **edit** via a drawer
  (name, code, address, phone, active), backed by the existing
  `/api/branches/` CRUD (`BranchViewSet`, `org` module).
- `lib/api.js` gained an `org` group (`branches`, `createBranch`,
  `updateBranch`); RBAC-gated by `canRead("org")` / `canWrite("org")`.

This closes the loop across the branch work: **create branches here → assign a
user to a branch in the user form → that branch-scoped user's records filter to
their branch** (the backend enhancement).

## Verifications actually run here

- All frontend JSX/JS pass a `tsc` syntax check (no TS1xxx/TS17xxx).
- Payload matches `BranchSerializer` (`name`, `code`, `address`, `phone`,
  `is_active`; `company` forced server-side).
- The screen is one of ten real module screens now; the `[module]` catch-all
  remains only as a fallback.

## Deliberately left out

- **Departments** management (the `/api/departments/` CRUD exists; same pattern
  could add it here).
- **Deactivation guards** (e.g. warning when a branch still has assigned users
  or warehouses) — deactivation is a simple flag for now.

## Known caveat (same as everywhere)

- **Not built/run live here** — `next build`/`next lint` need `npm install`
  (network), so they run in CI. JSX verified with `tsc`.
