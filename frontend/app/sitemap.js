import { MARKETING_PATHS } from "@/lib/locale";
import { MARKETING_LANGUAGES, marketingUrl } from "@/lib/marketingMeta";
import { SITE_URL } from "@/lib/site";

// Written to out/sitemap.xml at export time. Every public page is listed once
// per language, each entry naming the other language as an alternate, all on
// the canonical host; the signed-in app is noindex.
export const dynamic = "force-static";

const PRIORITY = { "/": 1, "/product": 0.9, "/pricing": 0.9, "/register": 0.7 };

export default function sitemap() {
  const lastModified = new Date();
  return MARKETING_PATHS.flatMap((path) => {
    const languages = Object.fromEntries(
      MARKETING_LANGUAGES.map((l) => [l, `${SITE_URL}${marketingUrl(path, l)}`])
    );
    return MARKETING_LANGUAGES.map((language) => ({
      url: languages[language],
      lastModified,
      changeFrequency: "weekly",
      priority: PRIORITY[path] ?? 0.5,
      alternates: { languages },
    }));
  });
}
