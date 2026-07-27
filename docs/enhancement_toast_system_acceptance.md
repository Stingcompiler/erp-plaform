# Enhancement: Shared Toast System

Status: **built, in review.** A consistent, app-wide feedback mechanism to
replace ad-hoc inline messages.

## What was built

- **`components/ui/Toast.jsx`** — a `ToastProvider` context + `useToast()` hook
  exposing `success` / `error` / `info` / `push`. Toasts auto-dismiss (4s
  default, configurable), stack bottom-center, are dismissible, and are styled
  per tone (ok / danger / neutral) using the existing design tokens. The hook is
  safe to call outside a provider (no-op), so components never crash.
- **Mounted** once in `app/(app)/layout.jsx`, wrapping the app shell, so every
  authenticated screen can raise toasts.
- **Wired as the reference usage** into the two highest-traffic flows:
  - **POS checkout** — "Sale recorded" on success, error toast on failure
    (inline error kept too).
  - **Stock receiving** — "Stock received" / error toast.

Other screens keep their inline messages and can adopt `useToast()`
incrementally — the system is additive and non-breaking.

## Verifications actually run here

- All frontend JSX/JS pass a `tsc` syntax check (no TS1xxx/TS17xxx).
- Provider is mounted above all `(app)` routes; the hook degrades to a no-op if
  ever used outside the provider.

## Deliberately left out

- **Migrating every form** to toasts (POS + receiving done as the pattern;
  inventory/sales/purchasing/returns/users/website/settings still use inline
  messages, which continue to work).
- **Action toasts** (e.g. an "Undo" button) — messages only for now.
- **Queued de-duplication** of identical rapid toasts.

## Known caveat (same as everywhere)

- **Not built/run live here** — `next build`/`next lint` need `npm install`
  (network), so they run in CI. JSX verified with `tsc`.
