// schema.org descriptions of the platform, rendered by components/seo/JsonLd.
// Search engines use these for rich results (organization panel, software
// listing, FAQ dropdowns under the snippet). The site-wide blocks are Arabic
// (the default document language); the per-page blocks follow the page's
// language. Keep them in step with lib/marketingI18n.js.
import { homeAr, homeEn, pricingAr, pricingEn } from "./marketingI18n";
import { marketingCopy, marketingUrl } from "./marketingMeta";
import { OG_IMAGE, SITE_NAME, SITE_NAME_LATIN, SITE_URL } from "./site";

const ORGANIZATION_ID = `${SITE_URL}/#organization`;
const APPLICATION_ID = `${SITE_URL}/#software`;

export function organizationJsonLd() {
  return {
    "@context": "https://schema.org",
    "@type": "Organization",
    "@id": ORGANIZATION_ID,
    name: SITE_NAME_LATIN,
    alternateName: SITE_NAME,
    url: `${SITE_URL}/`,
    logo: `${SITE_URL}/icons/icon-512.png`,
    image: `${SITE_URL}${OG_IMAGE.url}`,
    areaServed: ["SD", "SA", "AE", "QA", "KW", "BH", "OM", "EG"],
    availableLanguage: ["ar", "en"],
  };
}

export function softwareApplicationJsonLd() {
  return {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    "@id": APPLICATION_ID,
    name: SITE_NAME_LATIN,
    alternateName: SITE_NAME,
    url: `${SITE_URL}/`,
    applicationCategory: "BusinessApplication",
    applicationSubCategory: "ERP, POS, Inventory",
    operatingSystem: "Web, Android, iOS, Windows, macOS",
    inLanguage: ["ar", "en"],
    description:
      "منصة سحابية لإدارة المبيعات والمخزون والمشتريات وديون العملاء للمحلات وتجار الجملة والموزعين، مع نقطة بيع تعمل بلا إنترنت وفروع متعددة.",
    featureList: [
      "نقطة بيع تعمل بلا إنترنت وتزامن تلقائي",
      "مخزون بالدفعات وتواريخ الصلاحية (FEFO)",
      "دفتر ديون العملاء وكشوف الحساب",
      "فروع ومستودعات متعددة",
      "واجهة عربية وإنجليزية من اليمين لليسار",
      "تشغيل على السحابة أو على خادمك الخاص",
    ],
    screenshot: `${SITE_URL}/marketing/dashboard.png`,
    image: `${SITE_URL}${OG_IMAGE.url}`,
    publisher: { "@id": ORGANIZATION_ID },
    offers: {
      "@type": "Offer",
      url: `${SITE_URL}/pricing/`,
      // Free trial; the paid plans are listed on /pricing and change without
      // a deploy, so no fixed price is claimed here.
      price: "0",
      priceCurrency: "USD",
      description: "تجربة مجانية 14 يومًا بلا بطاقة",
    },
  };
}

export function faqJsonLd(pairs) {
  return faqPage(pairs);
}

export function breadcrumbJsonLd(items, language = "ar") {
  // items: [[name, path]] from the home page down to the current page.
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items.map(([name, path], index) => ({
      "@type": "ListItem",
      position: index + 1,
      name,
      item: `${SITE_URL}${marketingUrl(path, language)}`,
    })),
  };
}

export function articleJsonLd({ path, language, title, description, published, modified, minutes }) {
  return {
    "@context": "https://schema.org",
    "@type": "Article",
    headline: title,
    description,
    inLanguage: language,
    datePublished: published,
    dateModified: modified,
    timeRequired: `PT${minutes}M`,
    mainEntityOfPage: `${SITE_URL}${marketingUrl(path, language)}`,
    image: `${SITE_URL}${OG_IMAGE.url}`,
    author: { "@id": ORGANIZATION_ID },
    publisher: { "@id": ORGANIZATION_ID },
    about: { "@id": APPLICATION_ID },
  };
}

function faqPage(pairs) {
  return {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: pairs.map(([question, answer]) => ({
      "@type": "Question",
      name: question,
      acceptedAnswer: { "@type": "Answer", text: answer },
    })),
  };
}

// The same questions the page shows in that language; a FAQPage block whose
// content is not visible on the page is against Google's guidelines.
export const homeFaqJsonLd = (language = "ar") => faqPage((language === "en" ? homeEn : homeAr).faq);
export const pricingFaqJsonLd = (language = "ar") =>
  faqPage((language === "en" ? pricingEn : pricingAr).faq);

export function webPageJsonLd(path, language = "ar") {
  const { title, description } = marketingCopy(path, language);
  return {
    "@context": "https://schema.org",
    "@type": "WebPage",
    url: `${SITE_URL}${marketingUrl(path, language)}`,
    name: title,
    description,
    inLanguage: language,
    isPartOf: { "@type": "WebSite", url: `${SITE_URL}/`, name: SITE_NAME_LATIN },
    about: { "@id": APPLICATION_ID },
  };
}
