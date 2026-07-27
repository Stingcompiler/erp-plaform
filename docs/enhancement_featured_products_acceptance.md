# Enhancement: Featured Products Management

Status: **built, in review.** The final item — completes the public-site builder.

## What was built

A **Featured products** manager on the Website screen
(`components/website/FeaturedProducts.jsx`), backed by the existing
`/api/website/featured-products/` CRUD:

- **List** of featured products ordered by `order`, showing the product name
  (resolved best-effort from the products list) and caption.
- **Add / edit** drawer: pick a product via debounced search, set a caption and
  order. Create sends the singleton `website` id; the serializer enforces that
  the product belongs to the caller's company.
- **Delete** (confirmed). RBAC-gated by `website` write.

Rendered on the Website page beneath the page fields and sections editor, so the
storefront can now be fully composed from the app: page details + publish,
content sections, and featured products.

## Verifications actually run here

- All frontend JSX/JS pass a `tsc` syntax check (no TS1xxx/TS17xxx).
- Payload matches `FeaturedProductSerializer` (`website`, `product`, `caption`,
  `order`; `company` forced server-side; product/website company-validated).

## Deliberately left out

- **Product image/thumbnail** in the list (the product name + caption are shown;
  images would need a product-image field not modelled here).
- **Drag-and-drop reordering** (numeric `order` for now).

## Known caveat (same as everywhere)

- **Not built/run live here** — `next build`/`next lint` need `npm install`
  (network), so they run in CI. JSX verified with `tsc`.
