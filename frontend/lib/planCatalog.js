// The public plan catalogue, normalized once for every pricing template.
//
// /api/public/plans/ returns one row per plan (its newest published
// version). The pricing page — whichever card template renders it — never
// reads those rows directly: it reads what normalizePlans() makes of them,
// so the rules live here and not in markup:
//
//   - order: the operator's sort_order, then the price, then the name;
//   - exactly one "most popular" badge (the first highlighted plan), even
//     if the data ever carries more than one;
//   - the price as one amount and ONE currency label (lib/money.js), with
//     free and price-on-request plans told apart;
//   - the card body from the real version data: the modules it includes
//     and its limits (an absent limit is uncapped, as the server enforces);
//   - the marketing feature lines only as extras after that, with every
//     line that repeats or contradicts the real modules/limits left out;
//   - no internal code or slug ever reaches the visitor.
//
// featureWarnings() is the same reading from the operator's side: the
// platform plans page lists the lines the pricing page would hide because
// they disagree with the plan.

import { foldArabic } from "./arabicFold.js";
import { currencyLabel } from "./money.js";
import { ALL_MODULES, CORE_MODULES, PLAN_MODULES } from "./planModules.js";

// Limits a plan may cap, in the order they are shown. storage_mb is priced,
// not counted, and only appears when a version sets it.
export const LIMIT_KEYS = ["users", "branches", "warehouses", "devices", "storage_mb"];
export const COUNTED_LIMITS = ["users", "branches", "warehouses", "devices"];

// Modules a plan can include or leave out; the core ones come with every
// plan (core.entitlements.CORE_MODULES) and are shown as one line.
export const GATED_MODULES = PLAN_MODULES.filter((code) => !CORE_MODULES.includes(code));

// ---- Text helpers ---------------------------------------------------------

// Lowercased, Arabic-folded, punctuation turned to spaces: the form two
// lines are compared in.
export function fold(text) {
  return foldArabic(String(text ?? ""))
    .toLowerCase()
    .replace(/(\d),(?=\d)/g, "$1")
    .replace(/[\p{P}\p{S}]+/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

// "economist", "bs-2", "erp_full": an operator's working label, not copy.
const SLUG = /^[a-z0-9]+(?:[-_][a-z0-9]+)*$/;
export function looksLikeSlug(text) {
  return SLUG.test(String(text ?? "").trim());
}

const HAS_ARABIC = /\p{Script=Arabic}/u;

// A name typed as a slug ("business", "pro-plus") reads as words.
function humanize(name) {
  const raw = String(name ?? "").trim();
  if (!looksLikeSlug(raw)) return raw;
  return raw.split(/[-_]/).map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join(" ");
}

// ---- Price ----------------------------------------------------------------

// { kind: "paid", amount, currency } | { kind: "free" } | { kind: "custom" }
export function planPrice(row) {
  const raw = row?.price;
  const amount = Number(raw);
  if (raw === null || raw === undefined || raw === "" || !Number.isFinite(amount) || amount < 0) {
    return { kind: "custom" };
  }
  if (amount === 0) return { kind: "free" };
  return { kind: "paid", amount, currency: row.currency || "" };
}

const WHOLE = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const CENTS = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

// "500,000 ج.س" / "500,000 SDG": Latin digits like everywhere in the app,
// whole amounts without ".00" (a price list, not a ledger), and the currency
// label once — never the ISO code and the symbol side by side.
export function formatPlanAmount(amount, currency, language = "ar") {
  const n = Number(amount);
  if (!Number.isFinite(n)) return "";
  const figure = Number.isInteger(n) ? WHOLE.format(n) : CENTS.format(n);
  const label = currencyLabel(currency, language);
  return label ? `${figure} ${label}` : figure;
}

// ---- Feature lines vs. the real plan --------------------------------------

// Words that name a limit, in either language (folded forms for Arabic).
const LIMIT_WORDS = {
  users: ["users?", "seats?", "مستخدم\\S*"],
  branches: ["branch(?:es)?", "فرع\\S*", "فروع\\S*", "الفروع"],
  warehouses: ["warehouses?", "مستودع\\S*", "مخزن", "مخازن"],
  devices: ["devices?", "جهاز\\S*", "اجهز\\S*"],
};
const UNLIMITED = /\b(?:unlimited|no limit|uncapped)\b|بلا حد|غير محدود|بدون حد|لا محدود/u;

function wordPattern(words) {
  // \b does not work around Arabic letters; a leading و/ب/ل/ال is allowed.
  return `(?<![\\p{L}\\p{N}])(?:[وفبلك])?(?:ال|لل)?(?:${words.join("|")})(?![\\p{L}\\p{N}])`;
}

// Each limit a line states: [{ key, value }] where value is a number or
// Infinity for "unlimited". "Up to 4 users, 4 branches" → users 4,
// branches 4; "حتى 4 مستخدمين و4 فروع" the same.
export function limitClaims(line) {
  const text = fold(line);
  const claims = [];
  for (const [key, words] of Object.entries(LIMIT_WORDS)) {
    const word = wordPattern(words);
    const before = new RegExp(`(\\d+)\\s+(?:\\S+\\s+)?${word}`, "gu");
    const after = new RegExp(`${word}\\s+(?:\\S+\\s+)?(\\d+)`, "gu");
    const numbers = [...text.matchAll(before)].map((m) => m[1]);
    if (!numbers.length) numbers.push(...[...text.matchAll(after)].map((m) => m[1]));
    for (const number of numbers) claims.push({ key, value: Number(number) });
    if (!numbers.length && UNLIMITED.test(text) && new RegExp(word, "u").test(text)) {
      claims.push({ key, value: Infinity });
    }
  }
  return claims;
}

// Words that name a plan-gated module. A group lists the modules any one of
// which makes the line true ("returns" is true with either kind).
const MODULE_WORDS = [
  { modules: ["inventory"], words: ["inventory", "stock", "مخزون"] },
  { modules: ["sales"], words: ["sales", "pos", "point of sale", "selling", "مبيعات", "نقطه بيع", "نقاط بيع", "نقطه البيع"] },
  { modules: ["purchasing"], words: ["purchasing", "purchases?", "purchase orders?", "suppliers?", "مشتريات", "موردين"] },
  { modules: ["sales_returns", "purchase_returns"], words: ["returns?", "مرتجع\\S*"] },
  { modules: ["crm"], words: ["crm", "customer relationship\\S*", "اداره العملاء", "علاقات العملاء"] },
  { modules: ["hr"], words: ["hr", "human resources", "payroll", "attendance", "موارد البشريه", "رواتب", "حضور والانصراف", "حضور"] },
  { modules: ["finance"], words: ["finance", "financial", "accounting", "expenses?", "ماليه", "محاسب\\S*", "مصروفات"] },
  { modules: ["reports"], words: ["reports?", "reporting", "analytics", "تقارير"] },
];

// The gated modules a line talks about, as groups: [["hr"], ["sales_returns", "purchase_returns"]].
export function moduleMentions(line) {
  const text = fold(line);
  return MODULE_WORDS
    .filter(({ words }) => new RegExp(wordPattern(words), "u").test(text))
    .map(({ modules }) => modules);
}

function includedSet(modules) {
  const list = modules || [];
  return new Set(list.includes(ALL_MODULES) ? PLAN_MODULES : list);
}

// What is wrong with one feature line against the plan's real modules and
// limits: [{ kind: "limit", key, claimed, actual }] (actual null = no cap)
// and/or [{ kind: "module", modules: [codes not included] }].
export function lineProblems(line, { modules, limits } = {}) {
  const problems = [];
  const caps = limits || {};
  for (const { key, value } of limitClaims(line)) {
    const actual = key in caps ? Number(caps[key]) : null;
    const claimed = value === Infinity ? null : value;
    if (claimed !== actual) problems.push({ kind: "limit", key, claimed, actual });
  }
  const included = includedSet(modules);
  const missing = moduleMentions(line)
    .filter((group) => !group.some((code) => included.has(code)))
    .flat();
  if (missing.length) problems.push({ kind: "module", modules: [...new Set(missing)] });
  return problems;
}

// For the platform plans page: every line, in either language, that the
// pricing page will hide because it disagrees with the plan.
export function featureWarnings({ features_en, features_ar, modules, limits }) {
  const warnings = [];
  for (const [language, text] of [["en", features_en], ["ar", features_ar]]) {
    for (const line of splitLines(text)) {
      for (const problem of lineProblems(line, { modules, limits })) {
        warnings.push({ language, line, ...problem });
      }
    }
  }
  return warnings;
}

export function splitLines(text) {
  if (Array.isArray(text)) return text.map((line) => String(line).trim()).filter(Boolean);
  return String(text ?? "").split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
}

// The feature lines a card shows after the real modules and limits: without
// repeats, without lines that only restate a module or limit label, without
// any line stating a limit (the limit rows say it, correctly), and without
// lines naming a module the plan does not include.
export function extraFeatures(lines, { modules, limits, labels = [] } = {}) {
  const seen = new Set(labels.map(fold).filter(Boolean));
  const extras = [];
  for (const line of splitLines(lines)) {
    const key = fold(line);
    if (!key || seen.has(key)) continue;
    seen.add(key);
    if (limitClaims(line).length) continue;
    if (lineProblems(line, { modules, limits }).length) continue;
    extras.push(line);
  }
  return extras;
}

// ---- The catalogue ---------------------------------------------------------

function pick(copy, language) {
  if (!copy) return "";
  return copy[language] || "";
}

// rows: the API response. language: "ar" | "en". labels(optional):
// { module(code) → label, limit(key) → label } in the UI language, so a
// feature line that merely repeats a row label is dropped.
export function normalizePlans(rows, language = "ar", labels = {}) {
  const list = Array.isArray(rows) ? rows : [];
  const sorted = [...list].sort((a, b) => {
    const order = (a.display?.sort_order ?? 100) - (b.display?.sort_order ?? 100);
    if (order) return order;
    const priceA = planPrice(a); const priceB = planPrice(b);
    const valueA = priceA.kind === "custom" ? Infinity : priceA.amount || 0;
    const valueB = priceB.kind === "custom" ? Infinity : priceB.amount || 0;
    if (valueA !== valueB) return valueA - valueB;
    return String(a.plan_name || "").localeCompare(String(b.plan_name || ""));
  });
  let badgeGiven = false;
  return sorted.map((row) => {
    const display = row.display || {};
    const included = includedSet(row.modules);
    const modules = GATED_MODULES.filter((code) => included.has(code));
    const limits = {};
    for (const key of LIMIT_KEYS) {
      const value = row.limits?.[key];
      if (value !== undefined && value !== null && Number.isFinite(Number(value))) limits[key] = Number(value);
    }
    const englishName = pick(display.name, "en") || row.plan_name || "";
    let name = pick(display.name, language) || englishName;
    name = humanize(name);
    let tagline = pick(display.tagline, language);
    // The server falls back to the English tagline for Arabic; an English
    // line on the Arabic page, or a slug typed as a tagline, is not copy.
    if (looksLikeSlug(tagline)) tagline = "";
    if (language === "ar" && tagline && !HAS_ARABIC.test(tagline) && tagline === pick(display.tagline, "en")) tagline = "";
    const lines = display.features?.[language]?.length ? display.features[language] : display.features?.en || [];
    const labelList = [
      ...GATED_MODULES.map((code) => labels.module?.(code)),
      ...CORE_MODULES.map((code) => labels.module?.(code)),
      ...LIMIT_KEYS.map((key) => labels.limit?.(key)),
    ].filter(Boolean);
    const highlighted = Boolean(display.is_highlighted) && !badgeGiven;
    if (highlighted) badgeGiven = true;
    return {
      id: row.id,
      name,
      tagline,
      price: planPrice(row),
      cycle: row.billing_cycle === "yearly" ? "yearly" : "monthly",
      trialDays: Number(row.trial_days) || 0,
      highlighted,
      allModules: (row.modules || []).includes(ALL_MODULES),
      modules,
      limits,
      extras: extraFeatures(lines, { modules: row.modules, limits: row.limits, labels: labelList }),
    };
  });
}

// The compare table from the same plans: module rows (only modules at least
// one plan includes) and limit rows (only limits at least one plan caps; an
// uncapped cell reads "unlimited").
export function compareMatrix(plans) {
  const list = plans || [];
  const modules = GATED_MODULES
    .filter((code) => list.some((plan) => plan.modules.includes(code)))
    .map((code) => ({ code, cells: list.map((plan) => plan.modules.includes(code)) }));
  const limits = LIMIT_KEYS
    .filter((key) => list.some((plan) => key in plan.limits))
    .map((key) => ({ key, cells: list.map((plan) => (key in plan.limits ? plan.limits[key] : null)) }));
  return { modules, limits };
}
