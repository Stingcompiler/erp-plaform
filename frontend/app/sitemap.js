import { PUBLIC_PATHS, SITE_URL } from "@/lib/site";

// Written to out/sitemap.xml at export time. Only the marketing pages are
// listed, every one on the canonical host; the signed-in app is noindex.
export const dynamic = "force-static";

const PRIORITY = { "/": 1, "/product/": 0.9, "/pricing/": 0.9, "/register/": 0.7 };

export default function sitemap() {
  const lastModified = new Date();
  return PUBLIC_PATHS.map((path) => ({
    url: `${SITE_URL}${path}`,
    lastModified,
    changeFrequency: "weekly",
    priority: PRIORITY[path] ?? 0.5,
  }));
}
