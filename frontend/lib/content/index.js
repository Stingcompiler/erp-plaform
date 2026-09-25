// Every content page the marketing site publishes, as root-relative Arabic
// paths (no /en prefix, no trailing slash) plus the title/description each
// language uses for <title>, meta description and the sitemap. The static
// pages (home, product, pricing, register) are in lib/marketingMeta.js;
// this module covers the pages generated from lib/content/*.
import { COMPARISONS } from "./compare";
import { GUIDES } from "./guides";
import { SOLUTIONS } from "./solutions";

export const SOLUTIONS_INDEX_PATH = "/solutions";
export const GUIDES_INDEX_PATH = "/guides";

export const INDEX_COPY = {
  [SOLUTIONS_INDEX_PATH]: {
    ar: {
      title: "الحلول — ما يحلّه فيزانو لكل نوع من الأعمال",
      metaTitle: "حلول فيزانو — إدارة الشركات متعددة الفروع، نقطة بيع بلا إنترنت، مخزون بالصلاحية، ديون العملاء",
      description:
        "صفحة لكل مشكلة تواجهها المتاجر والشركات بفرع أو عدة فروع: إدارة الفروع والمستودعات والأدوار، البيع أثناء انقطاع الإنترنت، المخزون بالدفعات وتواريخ الصلاحية، ديون العملاء وكشوف الحساب، وصفحة عامة للشركة.",
    },
    en: {
      title: "Solutions — what Vezano solves for each kind of business",
      metaTitle: "Vezano solutions — multi-branch company management, offline POS, expiry-tracked inventory, customer debts",
      description:
        "A page for each problem stores and companies with one branch or many face: running branches, warehouses and roles, selling through internet outages, batch and expiry inventory, customer debts and statements, and a public company page.",
    },
  },
  [GUIDES_INDEX_PATH]: {
    ar: {
      title: "أدلة عملية لإدارة المتاجر والشركات",
      metaTitle: "أدلة عملية للمتاجر والشركات بفرع أو عدة فروع — البيع بلا إنترنت، جرد المخزون، تحصيل الديون",
      description:
        "مقالات قصيرة وعملية لأصحاب المتاجر والشركات ومديري الفروع: كيف يستمر البيع أثناء الانقطاع، كيف تجرد المتجر أو المستودع دون إغلاق، وكيف تحصّل الديون دون خسارة العملاء.",
    },
    en: {
      title: "Practical guides for running stores and companies",
      metaTitle: "Practical guides for stores and companies with one branch or many — selling offline, stock counts, collecting debts",
      description:
        "Short, practical articles for store and company owners and branch managers: how to keep selling through outages, how to count a store or warehouse without closing, and how to collect debts without losing customers.",
    },
  },
};

function copyOf(item, language) {
  const text = item[language];
  return { title: text.metaTitle || text.title, description: text.description };
}

// [{ path, ar: {title, description}, en: {...} }] for every generated page.
export function contentPages() {
  const pages = [];
  for (const [path, copy] of Object.entries(INDEX_COPY)) {
    pages.push({
      path,
      ar: { title: copy.ar.metaTitle, description: copy.ar.description },
      en: { title: copy.en.metaTitle, description: copy.en.description },
    });
  }
  for (const item of SOLUTIONS) {
    pages.push({ path: `${SOLUTIONS_INDEX_PATH}/${item.slug}`, ar: copyOf(item, "ar"), en: copyOf(item, "en") });
  }
  for (const item of GUIDES) {
    pages.push({ path: `${GUIDES_INDEX_PATH}/${item.slug}`, ar: copyOf(item, "ar"), en: copyOf(item, "en") });
  }
  for (const item of COMPARISONS) {
    pages.push({ path: `/compare/${item.slug}`, ar: copyOf(item, "ar"), en: copyOf(item, "en") });
  }
  return pages;
}

