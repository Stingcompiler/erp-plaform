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
      title: `${SITE_NAME} | نظام كاشير ومخزون وديون للمحلات والبقالات يعمل بلا إنترنت`,
      description:
        "فيزانو لأصحاب المحلات والبقالات: بِع بالباركود، وتابع المخزون وديون الزبائن، والبيع يستمر حين تنقطع الشبكة أو الكهرباء ويُزامَن عند عودتها. بالعربية والإنجليزية. تجربة مجانية 14 يومًا بلا بطاقة، وتفعيل في نفس اليوم بعد المراجعة.",
    },
    "/product": {
      title: "المنتج — نقطة البيع والمخزون والمشتريات والديون والفروع في نظام واحد",
      description:
        "كل ما يفعله فيزانو وحدة بوحدة: كاشير يعمل بلا إنترنت، مخزون بالدفعات والصلاحية، مشتريات ومرتجعات، دفتر ديون العملاء، تقارير، فروع ومستودعات متعددة، موارد بشرية وعملاء.",
    },
    "/pricing": {
      title: "الأسعار والباقات — تجربة مجانية 14 يومًا أو رخصة دائمة لخادمك",
      description:
        "باقات فيزانو للمحلات والموزعين: أسعار واضحة بلا رسوم على كل عملية. كل باقة تشمل العربية والإنجليزية ونقطة بيع تعمل بلا اتصال وصلاحيات حسب الدور، أو رخصة دائمة على خادمك الخاص.",
    },
    "/register": {
      title: "ابدأ تجربة شركتك المجانية",
      description:
        "سجّل شركتك في فيزانو: تجربة 14 يومًا بلا بطاقة على السحابة، أو اطلب عرض رخصة دائمة لخادمك الخاص. نراجع الطلب ونفعّل مساحة العمل في نفس اليوم ونرسل للمالك رابط التفعيل.",
    },
    "/register/hosting": {
      title: "السحابة أم خادمك الخاص؟ — الفرق بين خياري تشغيل فيزانو",
      description:
        "فيزانو على السحابة: لا تركيب، تحديثات ونسخ احتياطي ليلي علينا، اشتراك بالباقة. أو على خادمك الخاص: بياناتك عندك، رخصة دائمة، يعمل دون إنترنت. اعرف أيهما يناسب شركتك.",
    },
  },
  en: {
    "/": {
      title: `${SITE_NAME_LATIN} | Till, Stock and Debt Ledger for Shops and Groceries — Works Offline`,
      description:
        "Vezano for shop and grocery owners: sell by barcode, track stock and customer debts, and keep selling when the network or power drops — it syncs when it is back. Arabic and English. 14-day free trial, no card, activated the same day after review.",
    },
    "/product": {
      title: "Product — POS, Inventory, Purchasing, Receivables and Branches in One System",
      description:
        "Everything Vezano does, module by module: an offline-capable cashier, batch and expiry inventory, purchasing and returns, a customer debt ledger, reports, multiple branches and warehouses, HR and CRM.",
    },
    "/pricing": {
      title: "Pricing — 14-Day Free Trial or a Perpetual Licence for Your Own Server",
      description:
        "Vezano plans for shops and distributors: clear prices, no per-transaction fees. Every plan includes Arabic and English, an offline POS and role-based access, or a perpetual licence on your own server.",
    },
    "/register": {
      title: "Start Your Company's Free Trial",
      description:
        "Register your company on Vezano: a 14-day cloud trial with no card, or request a perpetual-licence quote for your own server. We review the request, activate the workspace the same day and send the owner an activation link.",
    },
    "/register/hosting": {
      title: "Cloud or Your Own Server? — Vezano's Two Ways to Run",
      description:
        "Vezano in the cloud: nothing to install, updates and nightly backups on us, a plan subscription. Or on your own server: data stays with you, a perpetual licence, runs without internet. Find out which fits your company.",
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
