# Enhancement: Website Sections Editor

Status: **built, in review.** Completes the public-site builder — the Website
screen now manages repeatable content sections, not just page-level fields.

## What was built

A **Page sections** editor on the Website screen (`SectionsEditor`), backed by
the existing `/api/website/sections/` CRUD:

- **List** of sections ordered by their `order`, showing type badge, title, a
  snippet of the body text, and a **Hidden** badge when not visible.
- **Add / edit** drawer: `type` (hero / about / products / gallery / contact /
  custom), `title`, `order`, visibility, and a **body** textarea saved into
  `content.text` — **merged** with any existing `content` keys so richer
  content set via the API is preserved.
- **Inline visibility toggle** (eye), **edit**, and **delete** (confirmed) per
  section. Create sends the singleton `website` id (read from the page GET,
  which includes `id`).

RBAC-gated by `website` write; read-only roles see the list without controls.

## Verifications actually run here

- All frontend JSX/JS pass a `tsc` syntax check (no TS1xxx/TS17xxx).
- Payloads match `SectionSerializer` (`type`, `title`, `order`, `content`,
  `is_visible`, plus `website` on create); type values match the model's
  `TYPE_CHOICES`.

## Deliberately left out

- **Drag-and-drop reordering** (order is edited as a number for now).
- **Per-type structured content** (e.g. hero heading/subheading/image, gallery
  image lists) — a single body text field for now, with other content keys
  preserved on save.
- **Featured products** management (`/api/website/featured-products/` exists;
  no UI yet).

## Known caveat (same as everywhere)

- **Not built/run live here** — `next build`/`next lint` need `npm install`
  (network), so they run in CI. JSX verified with `tsc`.
