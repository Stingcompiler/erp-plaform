# M1 — Auth, Users, Roles, Company/Branch/Department

Status: **built, in review.**

## What was built

**Custom identity model (`accounts`)**
- Email-login custom `User` (`AUTH_USER_MODEL = accounts.User`) with FKs to
  `company`, `branch`, `role`. `company` is nullable only for platform-level
  Super Administrators; every other user is bound to one company.
- `Role` (fixed 11-role set, tagged by `scope_level`
  platform/business/branch) and application-level `Permission` model, plus a
  `seed_roles` management command (idempotent, run on deploy).
- `is_platform_admin` property — the single switch that exempts Super
  Administrators from company scoping.

**Cookie-based JWT auth (PROJECT_RULES: JWT via HttpOnly cookies)**
- `CookieJWTAuthentication` reads the access token from an HttpOnly cookie,
  not the Authorization header — set as the DRF default auth class.
- `POST /api/auth/login/` sets HttpOnly access + refresh cookies;
  `POST /api/auth/logout/` blacklists the refresh token and clears cookies;
  `POST /api/auth/refresh/` re-issues the access cookie; `GET /api/auth/me/`
  returns the current user. Cookies are `Secure` outside dev, `SameSite=Lax`.

**Company scoping — Rule #1**
- `core/scoping.py`: `CompanyScopedQuerySetMixin` filters every queryset to
  `request.user.company_id` and forces `company` from the user on create
  (never from the request body). `CompanyScopedModelViewSet` bundles it with
  audit logging so both are inherited, not re-added per view. Enforced in the
  shared base viewset rather than middleware, because DRF authenticates inside
  the view — documented in settings and in the mixin. Rule #1 explicitly
  permits the mixin approach.
- `Company`/`Branch`/`Department` CRUD (`org` app). Company is the tenant root
  (scoped by PK to the user's own company; writes restricted to platform
  admins). Branch/Department inherit the scoped base viewset.

**Audit log — Rule #8**
- `core.ActivityLog` (append-only per Rule #9; admin is read-only) with a
  central `log_activity` helper. Login, logout, and every create/update/delete
  on the M1 CRUD resources write to it.

**Tax profile — Rule #7**
- `org.TaxProfile` auto-created for every Company with a flat-rate "simple"
  default, so no company exists without one and nothing hardcodes country
  assumptions. Pluggable invoice *behavior* remains M11; the model exists now
  so M11 needs no schema rewrite.

## Acceptance criteria

| Criterion | Result |
|---|---|
| Company A user can never retrieve Company B data, incl. by guessing IDs | **Covered by tests** (`CrossCompanyIsolationTests`: list excludes other company; retrieve/update/delete of another company's ID all return 404; create is forced into the caller's company). Proven by code + CI, not a live run here — see caveat. |
| Login/logout appear in Activity Log with user, company, timestamp | **Covered by tests** (`ActivityLogTests`). |

## Verifications actually run in this environment

- Every backend `.py` (including all three migrations) compiles.
- Manual lint pass: no non-migration line >100 chars; no trailing whitespace
  (migrations are excluded from flake8 per `.flake8`).
- `render.yaml` still valid; no Docker artifacts anywhere.

## Deliberately deferred / left out

- **Fine-grained per-permission enforcement.** Role/Permission are modeled and
  seeded, and company scoping + platform-admin gating are enforced, but
  per-action RBAC checks (e.g. "HR Officer can't touch Sales") are wired in
  **M6** where role-based visibility is the explicit acceptance criterion.
- **Frontend auth UI.** M1's build list is backend auth/models/scoping; login
  screens and the Context-API auth provider are not part of this milestone.
- **Refresh-token rotation.** Logout blacklists; rotation-on-refresh is off
  (`ROTATE_REFRESH_TOKENS = False`) to keep M1 simple — revisit under M10
  security hardening.
- **Password policy enforcement** (M10) — only the DRF min-length is applied.

## Known caveats to verify at first deploy

- **Tests were NOT executed live** — no network to install Django/DRF here.
  The suite is written (`accounts/tests.py`, `core/tests.py`) and all code is
  syntax-verified; the green run must come from CI.
- **Migrations were hand-authored** (no `makemigrations` available offline).
  CI now runs `python manage.py makemigrations --check --dry-run`, which fails
  if the hand-written migrations don't exactly match the models — so a
  mismatch is caught on first push and regenerating is one command. Confirm
  this step passes before the first deploy.

## Next

M2 — Inventory Core. Not started in this session (per PROJECT_RULES). Say
"continue" to proceed.
