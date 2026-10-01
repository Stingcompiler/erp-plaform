// Title/description per public page and language, and the metadata object a
// route layout exports. Every page declares both language versions as
// alternates (hreflang), with the Arabic root as x-default: it is the market
// the platform sells into first, and what an unknown-language visitor gets.
import { contentPages } from "./content";
import { localizePath } from "./locale";
import { OG_IMAGE, SITE_NAME, SITE_NAME_LATIN } from "./site";

const COPY = {
  ar: {
    "/": {
      title: `${SITE_NAME} | إدارة متكاملة لشركتك وفروعها… والبيع لا يتوقف`,
      description:
        "فيزانو برو يدير شركتك أو متجرك بكل فروعها: نقطة البيع والمخزون والمشتريات والموظفون والإدارة المالية والتقارير، والبيع يستمر عند انقطاع الشبكة.",
    },
    "/product": {
      title: "المبيعات والمخزون والإدارة المالية في نظام واحد",
      description:
        "كل وحدات فيزانو برو: كاشير يعمل بلا إنترنت، مخزون بالدفعات والصلاحية، مشتريات، عملاء وتحصيل، موظفون ورواتب، إدارة مالية وتقارير، وفروع بصلاحيات لكل دور.",
    },
    "/pricing": {
      title: "الأسعار والباقات — تجربة مجانية 14 يومًا",
      description:
        "باقات فيزانو برو بأسعار واضحة وبلا رسوم على كل عملية، وفي كل باقة نقطة بيع تعمل بلا اتصال وصلاحيات حسب الدور. أو رخصة دائمة على خادمك الخاص.",
    },
    "/register": {
      title: "ابدأ تجربة شركتك المجانية",
      description:
        "سجّل شركتك في فيزانو برو: تجربة 14 يومًا بلا بطاقة، أو عرض رخصة دائمة لخادمك الخاص. نراجع الطلب ونفعّل مساحة العمل في نفس اليوم.",
    },
    "/register/hosting": {
      title: "السحابة أم خادمك الخاص؟ — الفرق بين خياري تشغيل فيزانو برو",
      description:
        "على السحابة: لا تركيب، والتحديثات والنسخ الاحتياطي الليلي علينا. على خادمك: بياناتك عندك برخصة دائمة وتعمل دون إنترنت. اعرف أيهما يناسب شركتك.",
    },
  },
  en: {
    "/": {
      title: `${SITE_NAME_LATIN} | Manage Every Branch and Keep Selling Offline`,
      description:
        "Vezano Pro runs your company or store across every branch: POS, stock, purchasing, HR, financial management and reports, and sales go on when the network drops.",
    },
    "/product": {
      title: "POS, Inventory, HR and Financial Management",
      description:
        "Every Vezano Pro module: an offline-capable till, batch and expiry stock, purchasing, customers and collections, HR and payroll, and financial management.",
    },
    "/pricing": {
      title: "Pricing and Plans — 14-Day Free Trial",
      description:
        "Vezano Pro plans with clear prices and no per-transaction fees. Every plan has an offline POS and role-based access. Or a perpetual licence on your server.",
    },
    "/register": {
      title: "Start Your Company's Free Trial",
      description:
        "Register your company on Vezano Pro: a 14-day trial with no card, or a perpetual-licence quote for your own server. We review it and activate it the same day.",
    },
    "/register/hosting": {
      title: "Cloud or Your Own Server? — Vezano Pro's Two Ways to Run",
      description:
        "In the cloud: nothing to install, with updates and nightly backups on us. On your own server: your data stays with you on a perpetual licence. See which fits.",
    },
  },
};

export const MARKETING_LANGUAGES = Object.keys(COPY);

// Exported path (with trailing slash) for a page in a language.
export function marketingUrl(path, language) {
  const localized = localizePath(path, language);
  return localized.endsWith("/") ? localized : `${localized}/`;
}

let generated = null;
function generatedCopy(path, language) {
  if (!generated) {
    generated = {};
    for (const page of contentPages()) generated[page.path] = page;
  }
  return generated[path]?.[language];
}

export function marketingCopy(path, language) {
  const copy = COPY[language][path] || generatedCopy(path, language);
  if (!copy) throw new Error(`No marketing copy for ${path} (${language})`);
  return copy;
}

// Every public page, root-relative and without trailing slash.
export function allMarketingPaths() {
  return [...Object.keys(COPY.ar), ...contentPages().map((page) => page.path)];
}

export function marketingMetadata(path, language) {
  const { title, description } = marketingCopy(path, language);
  const canonical = marketingUrl(path, language);
  const languages = Object.fromEntries(MARKETING_LANGUAGES.map((l) => [l, marketingUrl(path, l)]));
  languages["x-default"] = marketingUrl(path, "ar");
  const brand = language === "en" ? SITE_NAME_LATIN : SITE_NAME;
  return {
    // The home title is the full brand line and must not get the suffix; it
    // also carries the template so the pages below read "Page | Brand".
    title: path === "/" ? { absolute: title, template: `%s | ${brand}` } : title,
    description,
    alternates: { canonical, languages },
    // Next replaces a parent's openGraph/twitter objects wholesale rather than
    // merging them, so the site-wide parts are repeated here.
    openGraph: {
      type: "website",
      siteName: SITE_NAME_LATIN,
      images: [OG_IMAGE],
      title,
      description,
      url: canonical,
      locale: language === "en" ? "en_US" : "ar_AR",
      alternateLocale: language === "en" ? ["ar_AR"] : ["en_US"],
    },
    twitter: { card: "summary_large_image", images: [OG_IMAGE.url], title, description },
  };
}
