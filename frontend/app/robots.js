import { PRIVATE_PATH_PREFIXES, SITE_URL } from "@/lib/site";

// Written to out/robots.txt at export time; Django serves it from there. The
// signed-in app additionally carries a noindex meta tag (app/(app)/layout.jsx)
// so a new route is protected even before it is listed here.
export const dynamic = "force-static";

export default function robots() {
  return {
    rules: [{ userAgent: "*", allow: "/", disallow: PRIVATE_PATH_PREFIXES }],
    // The marketing sitemap is exported with the site; the second one is
    // rendered by Django and lists every published customer page (/s/…).
    sitemap: [`${SITE_URL}/sitemap.xml`, `${SITE_URL}/sitemap-sites.xml`],
    host: SITE_URL,
  };
}
