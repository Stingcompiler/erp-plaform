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

// The public pages themselves are listed in lib/locale.js (MARKETING_PATHS);
// each exists in Arabic at the root and in English under /en/.

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
  "/users/detail/",
  "/settings/",
  "/subscription/",
  "/website/",
  "/customer-records/",
  "/web-orders/",
  "/supplier-records/",
  "/platform/",
  "/platform-leads/",
  "/platform-plans/",
  "/platform-registrations/",
  "/platform-subscriptions/",
  "/platform-team/",
  "/platform-activity/",
  "/platform-seo/",
];

export const OG_IMAGE = {
  url: "/marketing/og.png",
  width: 1200,
  height: 630,
  alt: "فيزانو — منصة إدارة الأعمال: مبيعات ومخزون وتحصيل في مكان واحد",
};

// Used by the noindex layouts (login, activation, the whole signed-in app).
export const NOINDEX = { index: false, follow: false, nocache: true };
