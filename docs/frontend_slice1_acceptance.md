# Frontend — Slice 1: Foundation

Status: **built, in review.** (First frontend slice after the M0–M12 backend.)

## What was built

The Next.js app was scaffold-only through M12. This slice makes it a real,
authenticated application shell.

**Design system.** A deliberate identity — deep slate-navy (`--ink`) + teal
(`--accent`) on cool paper, **Sora** for display, **Inter** for body, and **IBM
Plex Mono** for figures (a "ledger" motif that ties to the append-only ledger at
the backend's core). Colors are RGB-channel tokens so opacity + a full **dark
mode** work; **Arabic/RTL** is wired (IBM Plex Sans Arabic in the stack, `dir`
flips on the document, logical properties + `ms-/me-/start-` utilities so the
whole shell mirrors).

**Auth + session (`AuthProvider`).** On load it calls `/api/auth/me/`,
`/api/rbac/access/`, and `/api/ops/preferences/`; exposes `login`, `logout`,
`user`, the RBAC `access` map, `preferences`, and a `canRead(module)` helper.
Login uses the HttpOnly-cookie flow (no token handling in JS).

**API layer (`lib/api.js`).** One `withCredentials` axios instance plus
intent-named helpers (`auth.login`, `rbac.access`, `prefs.update`,
`dashboard.get`).

**Login page.** Branded split layout; real error handling; redirects to
`/dashboard` on success and away from `/login` if already signed in.

**Role-aware app shell (the signature).** The left rail renders only the
sections the user's RBAC access map permits (`canRead`), with a teal active
indicator; a workspace badge shows company + role. The top bar carries
language (EN/ع) and theme (light/dark/system) toggles wired to
`/api/ops/preferences/`, plus sign-out. Unbuilt module routes resolve to a
friendly placeholder (or an access notice) via a single `[module]` catch-all —
no dead links.

**Dashboard.** Consumes `/api/dashboard/` and shows only the sections the role
can see (sales, inventory, low-stock, purchasing, returns), with figures in the
mono ledger face and semantic color for low-stock / pending returns.

**Route protection.** The `(app)` layout guards every app route — unauthenticated
users are bounced to `/login`; the root `/` redirects into the app.

## Verifications actually run here

- All JSX/JS pass a `tsc` **syntax** check (no TS1xxx/TS17xxx errors); config
  files pass `node --check`. Imports/exports cross-checked by hand.

## Deliberately deferred (next slices)

- **Module screens.** Inventory, POS/sales, purchasing, returns, reports,
  users, website, and settings are placeholders — the APIs are live; the CRUD
  UIs come next, one module per slice.
- **Data tables / forms / toasts** shared component kit.
- **Offline queue UI** on top of the M7 sync endpoints.
- **Real translation catalogs** (strings are currently English; the language
  toggle sets direction + preference, ready for i18n copy).

## Known caveat (same as backend)

- **Not built/run live here** — no network to `npm install`, so `next build`
  and `next lint` run in CI, not in this sandbox. JSX was syntax-verified with
  `tsc`.

## Next

Module slice 1 — Inventory (products list, stock levels, movements) — or POS,
depending on priority. Say which.
