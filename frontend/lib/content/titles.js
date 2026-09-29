// The slug and title of every solution and guide page, for the footer that
// every public page carries (components/marketing/Chrome.jsx). The full
// articles (lib/content/solutions.js, guides.js — ~90 KB) stay with the
// pages that show them. tests/contentTitles.test.mjs keeps this list equal
// to the articles' own slugs and titles.
export const SOLUTION_TITLES = [
  { slug: "multi-branch", ar: "نظام إدارة متكامل للشركات متعددة الفروع", en: "Integrated management for multi-branch companies" },
  { slug: "offline-pos", ar: "نقطة بيع تعمل بلا إنترنت", en: "A point of sale that works offline" },
  { slug: "inventory-expiry", ar: "مخزون بالدفعات وتواريخ الصلاحية", en: "Inventory by batch and expiry date" },
  { slug: "customer-debts", ar: "دفتر ديون العملاء", en: "Customer debt ledger" },
  { slug: "store-page", ar: "صفحة عامة لشركتك أو متجرك على الإنترنت", en: "A public web page for your company or store" },
];

export const GUIDE_TITLES = [
  { slug: "sell-during-outages", ar: "كيف تواصل البيع أثناء انقطاع الإنترنت والكهرباء", en: "How to keep selling through internet and power outages" },
  { slug: "stock-count-without-closing", ar: "كيف تجرد مخزونك دون إغلاق المتجر أو المستودع", en: "How to count your stock without closing the store or warehouse" },
  { slug: "collect-customer-debts", ar: "كيف تحصّل ديون العملاء دون أن تخسرهم", en: "How to collect customer debts without losing the customers" },
];
