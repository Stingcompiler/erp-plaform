# M6 CRM & HR — domain modules completion

Status: **built, in review.**

## Context

The build plan (§5) specifies **M6 = CRM & HR**. In the original build, the M6
slot was used for **Role-Based Visibility & Dashboards** (see `M6_acceptance.md`)
— the RBAC matrix already reserved `crm` and `hr` modules and the `CRM Officer` /
`HR Officer` roles, but the CRM and HR **domain models were never built**. This
note covers building them to close that gap.

## CRM (`backend/crm/`)

Models per plan: `CustomerGroup`, `Lead`, `FollowUp`, `Note`.
- `Lead` carries a 6-stage pipeline (`new → contacted → qualified → proposal →
  won/lost`), estimated value, optional segment/branch/assignee.
- `GET /api/leads/pipeline/` returns per-stage counts + value (drives the board).
- `FollowUp` (scheduled next-actions, mark-done stamps time) and `Note`
  (timestamped activity trail) are the activity tracking.
- Company-scoped via `CompanyScopedModelViewSet`; relational FKs narrowed to the
  request company in the serializer so cross-tenant attach is impossible.
- **8 tests** (`crm/tests.py`): tenancy, cross-company rejection, pipeline
  summary, open filter, follow-up completion, note authorship.

Frontend: `/crm` — pipeline stat tiles, stage filter chips, lead cards, and a
lead drawer with follow-up scheduling + notes timeline. Bilingual, mobile-first.

## HR (`backend/hr/`)

Models per plan: `Position`, `Employee`, `Attendance`, `LeaveRequest`,
`PerformanceRecord`, `EmployeeDocument`.
- `Employee` links optionally to branch/department/position and a login `User`.
- `Attendance` is unique per employee/day.
- `LeaveRequest` has `approve`/`reject` actions that stamp reviewer + time.
- `PerformanceRecord` (1–5 rating, reviewer from request user),
  `EmployeeDocument` (metadata + file URL).
- Company-scoped + RBAC-gated (`HR Officer` writes HR; other roles 403).
- **8 tests** (`hr/tests.py`): tenancy, cross-company FK rejection, attendance
  uniqueness, leave approval flow + bad-range validation, rating bounds, RBAC.

Frontend: `/hr` — headcount/active/on-leave/pending stat tiles, Employees +
Leave-requests tabs, employee drawer, and inline leave approve/reject. Bilingual,
mobile-first.

## Wiring

- `INSTALLED_APPS` += `crm`, `hr`; `config/urls.py` includes both; `core/rbac.py`
  `APP_MODULE` maps both app labels to their modules.
- Nav gains CRM + HR entries (RBAC-filtered).

## Also fixed in this pass (pre-existing bugs surfaced by running the suite)

- **Reports CSV export was broken**: `?format=csv` was intercepted by DRF's
  default `URL_FORMAT_OVERRIDE` → 404 before the view's manual CSV handler ran.
  Fixed with `URL_FORMAT_OVERRIDE = None`. (`reports/tests.py` now passes.)
- **Stale M0 backup-cron test** asserted the command prints "stub"; the command
  was fully implemented in M10 — updated to assert real completion output.
- **`ops/test_storage` restore test** created a duplicate globally-unique Role —
  reuse the existing one.
- **Monolithic HTML caching**: `core/frontend.py` now sends
  `Cache-Control: no-cache` on HTML (only hashed `_next/static` assets are
  long-cached), so a redeploy can't leave a browser on stale HTML pointing at
  removed chunks.

Full backend suite: **168 passed, 0 failed**. Frontend build + lint clean.
