// Public identity of the hosted SaaS, shared by the metadata exports, the
// robots/sitemap routes and the JSON-LD blocks. One place to change when the
// canonical host changes; the Django side keeps the same list in
// backend/config/settings.py (VEZANO_PUBLIC_HOSTS).
//
// The app is served on three hosts (vezano.app, www.vezano.app and the
// original enterprise.vezano.app). Only the first is advertised: every
// marketing page carries a canonical link back to it, so search engines fold
// the duplicates into one entry instead of splitting ranking between them.

export const SITE_URL = "https://vezano.app";
export const SITE_NAME = "فيزانو";
export const SITE_NAME_LATIN = "Vezano";

// Pages that exist for the public and belong in the sitemap. Trailing slashes
// match the static export (next.config.js trailingSlash) and what Django
// serves, so the canonical URL and the served URL are byte-identical.
export const PUBLIC_PATHS = ["/", "/product/", "/pricing/", "/register/"];

// Everything else is the signed-in application (or sign-in itself) and is
// kept out of the index: it renders nothing useful without a session, and
// letting it in would compete with the marketing pages for the brand query.
export const PRIVATE_PATH_PREFIXES = [
  "/api/",
  "/admin/",
  "/login/",
  "/activate-owner/",
  "/dashboard/",
  "/sales/",
  "/inventory/",
  "/purchasing/",
  "/returns/",
  "/reports/",
  "/finance/",
  "/debts/",
  "/crm/",
  "/hr/",
  "/labels/",
  "/logs/",
  "/org/",
  "/users/",
  "/settings/",
  "/subscription/",
  "/website/",
  "/customer-records/",
  "/supplier-records/",
  "/platform/",
  "/platform-leads/",
  "/platform-plans/",
  "/platform-registrations/",
  "/platform-subscriptions/",
  "/platform-team/",
];

export const OG_IMAGE = {
  url: "/marketing/og.png",
  width: 1200,
  height: 630,
  alt: "فيزانو — منصة إدارة الأعمال: مبيعات ومخزون وتحصيل في مكان واحد",
};

// Used by the noindex layouts (login, activation, the whole signed-in app).
export const NOINDEX = { index: false, follow: false, nocache: true };
