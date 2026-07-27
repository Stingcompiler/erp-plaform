# Frontend — Slice 7: Users, Website & Settings (admin)

Status: **built, in review.** This completes a real screen for every nav module.

## What was built

The three remaining admin/config screens. Contracts read from
`accounts/serializers.py`, `website/serializers.py`, and the M10/M11 endpoints
first, so payloads are exact.

**Users (`/users`).** Lists workspace users (email, name, role, active); a
create/edit drawer (`UserForm`) with a role dropdown from `/api/roles/`, active
toggle, and a min-10 password on create (matching the M10 policy). PATCHes
`full_name`/`role`/`is_active`; email is immutable on edit.

**Website (`/website`).** Edits the company landing page (`business_name`,
tagline, about, contact, address, logo, primary color) via
`GET/PATCH /api/website/page/`, plus a **Publish / Unpublish** toggle
(`/api/website/page/publish/`) and a note that the public site is served at
`/api/public/site/<slug>/`. Read-only for roles without `website` write.

**Settings (`/settings`).** Two panels:
- **Tax & invoicing** — edits the `TaxProfile` (country, flat rate,
  `invoice_format` from the live handler list, e-invoicing toggle) via the M11
  endpoints; switching format changes tax + rendering (Rule #7).
- **Backups** — "Back up now" (`POST /api/ops/backups/`) and a list of recent
  backup records with kind, status, record count, and size (M10).

All three are RBAC-gated (`users` / `website` / `settings`).

## Frontend status: all modules now have a real screen

| Module | Screen |
|---|---|
| Dashboard | role-scoped KPIs |
| Inventory | products, stock, adjustments |
| Sales | POS checkout + invoices + receipts |
| Purchasing | suppliers, receiving, bills |
| Returns | quarantine + disposition (Rule #5) |
| Reports | KPIs, bars, AR aging, CSV |
| Users | user + role management |
| Website | landing-page editor + publish |
| Settings | tax profile + backups |

The `[module]` catch-all remains only as a fallback for unknown routes.

## Verifications actually run here

- All frontend JSX/JS pass a `tsc` syntax check (no TS1xxx/TS17xxx).
- Payloads cross-checked against `UserSerializer` (email/full_name/role/
  is_active/password), `WebsiteSerializer` (page fields; is_published via the
  publish endpoint), and the tax/ops endpoints.

## Deliberately deferred

- **Website sections/featured-products** editing (page fields + publish only;
  the sections API exists).
- **Branch assignment** on users, and password reset for existing users.
- A shared **toast** system (inline messages for now).
- Cross-milestone **integration tests** and the deferred backend items (durable
  backup storage, FIFO costing, bank-transfer supplier payments, real
  e-invoicing).

## Known caveat (same as the rest)

- **Not built/run live here** — `next build`/`next lint` need `npm install`
  (network), so they run in CI. JSX verified with `tsc`.
