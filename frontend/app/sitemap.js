import { GUIDES } from "@/lib/content/guides";
import { GUIDES_INDEX_PATH } from "@/lib/content";
import { MARKETING_LANGUAGES, allMarketingPaths, marketingUrl } from "@/lib/marketingMeta";
import { SITE_URL } from "@/lib/site";

// Written to out/sitemap.xml at export time. Every public page is listed once
// per language, each entry naming the other language as an alternate, all on
// the canonical host; the signed-in app is noindex.
export const dynamic = "force-static";

const PRIORITY = { "/": 1, "/product": 0.9, "/pricing": 0.9, "/register": 0.7 };

function priorityOf(path) {
  if (path in PRIORITY) return PRIORITY[path];
  if (path.startsWith("/solutions/")) return 0.8;
  if (path.startsWith("/guides/") || path.startsWith("/compare/")) return 0.6;
  return 0.5;
}

// Guides carry their own modification date; everything else is "now", which
// is the export time and therefore the last deploy.
function modifiedOf(path, now) {
  const guide = GUIDES.find((item) => `${GUIDES_INDEX_PATH}/${item.slug}` === path);
  return guide ? new Date(guide.modified) : now;
}

export default function sitemap() {
  const now = new Date();
  return allMarketingPaths().flatMap((path) => {
    const languages = Object.fromEntries(
      MARKETING_LANGUAGES.map((l) => [l, `${SITE_URL}${marketingUrl(path, l)}`])
    );
    return MARKETING_LANGUAGES.map((language) => ({
      url: languages[language],
      lastModified: modifiedOf(path, now),
      changeFrequency: path.startsWith("/guides/") ? "monthly" : "weekly",
      priority: priorityOf(path),
      alternates: { languages },
    }));
  });
}
