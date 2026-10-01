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
      title: "الحلول — ما يحلّه فيزانو برو لكل نوع من الأعمال",
      metaTitle: "حلول للمتاجر والشركات بفرع أو عدة فروع",
      description:
        "صفحة لكل مشكلة تواجهها المتاجر والشركات بفرع أو عدة فروع: الفروع والأدوار، البيع أثناء انقطاع الإنترنت، المخزون بالصلاحية، ديون العملاء، وصفحة عامة.",
    },
    en: {
      title: "Solutions — what Vezano Pro solves for each kind of business",
      metaTitle: "Solutions for Stores and Multi-Branch Firms",
      description:
        "One page per problem for stores and companies with one branch or many: branches and roles, selling offline, expiry-tracked stock, debts, a public page.",
    },
  },
  [GUIDES_INDEX_PATH]: {
    ar: {
      title: "أدلة عملية لإدارة المتاجر والشركات",
      metaTitle: "أدلة عملية: البيع بلا إنترنت والجرد والتحصيل",
      description:
        "مقالات قصيرة لأصحاب المتاجر والشركات ومديري الفروع: كيف يستمر البيع أثناء الانقطاع، وكيف تجرد دون إغلاق، وكيف تحصّل الديون دون خسارة العملاء.",
    },
    en: {
      title: "Practical guides for running stores and companies",
      metaTitle: "Guides: Selling Offline, Stock Counts, Debts",
      description:
        "Short, practical articles for owners and branch managers: keep selling through outages, count stock without closing, and collect debts without losing customers.",
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

