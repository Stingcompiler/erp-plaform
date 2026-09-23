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
      metaTitle: "حلول فيزانو — نقطة بيع بلا إنترنت، مخزون بالصلاحية، ديون العملاء، فروع متعددة",
      description:
        "صفحة لكل مشكلة يواجهها التاجر: البيع أثناء انقطاع الإنترنت، المخزون بالدفعات وتواريخ الصلاحية، ديون العملاء وكشوف الحساب، وإدارة الفروع المتعددة.",
    },
    en: {
      title: "Solutions — what Vezano solves for each kind of business",
      metaTitle: "Vezano solutions — offline POS, expiry-tracked inventory, customer debts, multiple branches",
      description:
        "A page for each problem merchants face: selling through internet outages, batch and expiry inventory, customer debts and statements, and running multiple branches.",
    },
  },
  [GUIDES_INDEX_PATH]: {
    ar: {
      title: "أدلة عملية للتاجر",
      metaTitle: "أدلة عملية للمحلات وتجار الجملة — البيع بلا إنترنت، جرد المخزون، تحصيل الديون",
      description:
        "مقالات قصيرة وعملية عن مشاكل التجارة اليومية: كيف تبيع أثناء الانقطاع، كيف تجرد دون إغلاق، وكيف تحصّل الديون دون خسارة العملاء.",
    },
    en: {
      title: "Practical guides for merchants",
      metaTitle: "Practical guides for shops and wholesalers — selling offline, stock counts, collecting debts",
      description:
        "Short, practical articles on everyday trade problems: how to sell through outages, how to count stock without closing, and how to collect debts without losing customers.",
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

