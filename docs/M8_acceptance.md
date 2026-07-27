# M8 — Public Website / Landing Page Generator

Status: **built, in review.**

## What was built (`website` app)

**Auto-generated per-company site.** `Website` is a singleton per company. The
first authenticated `GET /api/website/page/` lazily generates a starter site
(business name from the company) plus default `hero`, `about`, and `contact`
sections, ready to edit and publish — no company can exist without the option
of a site, and nothing has to be built from a blank slate.

**Editable content.** `Section` (ordered, typed: hero/about/products/gallery/
contact/custom, with a free-form JSON `content` and a `is_visible` flag) and
`FeaturedProduct` (an explicit, opt-in curation of products to show publicly —
never the whole catalog). Both are company-scoped CRUD, gated to the `website`
module (M6) — so only a Landing Page Manager (or owner/GM) can edit. Publish is
a toggle at `POST /api/website/page/publish/`.

**Public endpoint.** `GET /api/public/site/<slug>/` is **unauthenticated**
(AllowAny, no RBAC), resolves exactly one company by its M1 `slug`, and returns
the site only if `is_published`. It serves only public-safe fields, only
visible sections, and — critically — featured products expose just name / sku /
price / caption (no cost price, stock, or reorder data).

## Acceptance criteria

| Criterion | Result |
|---|---|
| A company can build and edit a public landing page | **Covered by tests** — `EditAccessTests`: first GET auto-generates sections; PATCH edits content. |
| Editing requires the website role; others are denied | **Covered by tests** — a Sales Officer gets 403; a Landing Page Manager succeeds. |
| The public site serves published content by slug with no auth | **Covered by tests** — `PublicSiteTests`: anonymous GET by slug returns the site + sections. |
| Unpublished / unknown slug is not exposed | **Covered by tests** — unpublished and unknown slugs both 404. |
| Only published, visible, public-safe data is exposed; per-company isolation | **Covered by tests** — hidden sections excluded; featured products expose no internal fields; company B's slug (unpublished) 404s while A's serves. |

## Verifications actually run here

- All backend `.py` incl. the 3-model website migration compile; lint +
  unused-import checks clean. Added `"website": "website"` to the RBAC
  app→module map so the editing endpoints are gated (public endpoint is
  AllowAny and bypasses it).

## Deliberately deferred / left out

- **Server-side HTML rendering / theming templates.** The API returns
  structured JSON (sections + config); the Next.js frontend renders it. There's
  no server-rendered HTML page or theme engine here.
- **Custom domains / DNS.** Sites are served by company slug under the API, not
  at a customer's own domain.
- **Image uploads.** `logo_url` and gallery images are URLs; no media
  upload/storage pipeline (that's an infra concern).
- **SEO/sitemap, form submissions (contact form capture).** The contact section
  shows details; capturing public form submissions isn't built.

## Known caveats (unchanged)

- **Tests not executed live** — no network to install Django; suite written +
  syntax-verified, runs in CI, with the `makemigrations --check` gate.

## Next

M9 — Reports & Dashboards. Not started this session. Say "continue".
