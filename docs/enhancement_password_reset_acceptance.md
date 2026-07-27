# Enhancement: Admin Password Reset

Status: **built, in review.** Lets an authorized admin set a new password for an
existing user from the Users screen.

## Approach

There's no email/SMTP service configured (and no network here to test one), so a
token-by-email self-service reset isn't testable end to end. The useful,
verifiable interpretation is **admin-driven reset**: a company admin sets a new
password for a user in their company. The backend already supported this
(`UserSerializer.update()` applies `password` with the same
`AUTH_PASSWORD_VALIDATORS` + min-10 rule as create) — the only gap was the UI.

## What was built

- **User form (edit mode)** gained an optional **Reset password** field
  ("Leave blank to keep the current password"), sent on save only when filled.
  The save button enforces the 10-char minimum on a non-empty reset.
- **Backend test** (`accounts/test_password_reset.py`) documenting and pinning
  the capability.

## Acceptance criteria

| Criterion | Result |
|---|---|
| Admin can set another user's password | **Covered** — PATCH `{password}` → 200. |
| The user can log in with the new password | **Covered**. |
| The old password stops working | **Covered** — old creds → 400. |
| Too-short passwords are rejected | **Covered** — `short1` → 400. |
| Company scoping still holds | Enforced by `UserViewSet` (company-scoped); an admin can only reach their own company's users. |

## Verifications actually run here

- Frontend passes `tsc`; backend test compiles; lint + repo audit pass.
- Reuses the existing validated `password` write path — no new endpoint or
  migration.

## Deliberately left out

- **Self-service reset by email** (needs an email backend; wire SMTP/provider
  env + a token model + request/confirm endpoints to enable).
- **Forced password change on next login** and **password history**.

## Known caveat (same as everywhere)

- **Not executed live here** — no network to install Django / `npm install`;
  tests and build run in CI.
