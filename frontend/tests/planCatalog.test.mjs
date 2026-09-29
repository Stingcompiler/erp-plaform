import assert from "node:assert/strict";
import test from "node:test";

import {
  compareMatrix,
  extraFeatures,
  featureWarnings,
  formatPlanAmount,
  limitClaims,
  lineProblems,
  normalizePlans,
  planPrice,
} from "../lib/planCatalog.js";

// Shaped like the live /api/public/plans/ rows that prompted this: three
// plans with the same feature list, two of them highlighted, a slug typed
// as a tagline, a lowercase working name, "SD" and "SDG" side by side.
const FEATURES_EN = [
  "Sales and POS, offline",
  "Inventory with batches and expiry",
  "Up to 4 users, 4 branches, 4 warehouses",
  "Customer debts and statements",
  "Customer debts and statements",
  "Payroll and attendance",
  "Priority support",
];
const FEATURES_AR = [
  "مبيعات ونقطة بيع تعمل بلا اتصال",
  "حتى 4 مستخدمين و4 فروع و4 مستودعات",
  "دعم ذو أولوية",
];
const row = (id, extra) => ({
  id,
  plan_code: `code-${id}`,
  plan_name: `plan ${id}`,
  currency: "SDG",
  billing_cycle: "monthly",
  trial_days: 14,
  modules: ["inventory", "sales", "purchasing"],
  limits: { users: 4, branches: 4, warehouses: 4 },
  ...extra,
  display: {
    name: { en: `Plan ${id}`, ar: `باقة ${id}` },
    tagline: { en: "", ar: "" },
    features: { en: FEATURES_EN, ar: FEATURES_AR },
    is_highlighted: false,
    sort_order: 100,
    ...extra.display,
  },
});
const ROWS = [
  row(4, { price: "500000.00", display: { name: { en: "business", ar: "الأعمال" }, is_highlighted: true, sort_order: 10 } }),
  row(7, { price: "200000.00", currency: "SD", limits: { users: 2, devices: 2, branches: 1, warehouses: 1 }, display: { tagline: { en: "economist", ar: "economist" }, is_highlighted: true } }),
  row(6, { price: "2000000.00", modules: ["*"], limits: { users: 20, branches: 4, warehouses: 20 } }),
  row(9, { price: "0" }),
];

test("plans read in sort_order, then price; only the first highlighted keeps the badge", () => {
  const plans = normalizePlans(ROWS, "en");
  assert.deepEqual(plans.map((plan) => plan.id), [4, 9, 7, 6]);
  assert.deepEqual(plans.filter((plan) => plan.highlighted).map((plan) => plan.id), [4]);
});

test("no slug or code reaches the visitor", () => {
  const [business, , economy] = normalizePlans(ROWS, "en");
  assert.equal(business.name, "Business");
  assert.equal(economy.tagline, "");
  const arabic = normalizePlans(ROWS, "ar");
  assert.equal(arabic.find((plan) => plan.id === 7).tagline, "");
  const text = JSON.stringify(normalizePlans(ROWS, "ar"));
  assert.ok(!text.includes("code-"), text);
  assert.ok(!text.includes("economist"), text);
});

test("one currency label, whole amounts without .00; free and on-request plans", () => {
  assert.equal(formatPlanAmount(500000, "SDG", "ar"), "500,000 ج.س");
  assert.equal(formatPlanAmount(200000, "SD", "en"), "200,000 SDG");
  assert.equal(formatPlanAmount(19.5, "USD", "en"), "19.50 USD");
  assert.deepEqual(planPrice({ price: "0.00" }), { kind: "free" });
  assert.deepEqual(planPrice({ price: null }), { kind: "custom" });
  assert.equal(planPrice({ price: "10", currency: "SDG" }).kind, "paid");
});

test("modules come from the version ('*' = every gated one); limits keep only real caps", () => {
  const plans = normalizePlans(ROWS, "en");
  const economy = plans.find((plan) => plan.id === 7);
  assert.deepEqual(economy.modules, ["inventory", "sales", "purchasing"]);
  assert.deepEqual(economy.limits, { users: 2, branches: 1, warehouses: 1, devices: 2 });
  const full = plans.find((plan) => plan.id === 6);
  assert.equal(full.allModules, true);
  assert.ok(full.modules.includes("hr") && full.modules.includes("reports"));
  assert.ok(!full.modules.includes("users"), "core modules are one separate line");
});

test("feature extras drop repeats, limit statements and modules the plan lacks", () => {
  const economy = normalizePlans(ROWS, "en", { module: (code) => ({ inventory: "Inventory" })[code] })
    .find((plan) => plan.id === 7);
  assert.deepEqual(economy.extras, [
    "Sales and POS, offline",
    "Inventory with batches and expiry",
    "Customer debts and statements",
    "Priority support",
  ]);
  const full = normalizePlans(ROWS, "en").find((plan) => plan.id === 6);
  assert.ok(full.extras.includes("Payroll and attendance"), "HR is included with '*'");
  assert.deepEqual(
    extraFeatures(["Inventory", "Inventory with expiry", "inventory "], { modules: ["inventory"], labels: ["Inventory"] }),
    ["Inventory with expiry"],
  );
  const arabic = normalizePlans(ROWS, "ar").find((plan) => plan.id === 7);
  assert.deepEqual(arabic.extras, ["مبيعات ونقطة بيع تعمل بلا اتصال", "دعم ذو أولوية"]);
});

test("limit claims read numbers and 'unlimited' in English and Arabic", () => {
  assert.deepEqual(limitClaims("Up to 4 users, 4 branches, 4 warehouses"), [
    { key: "users", value: 4 }, { key: "branches", value: 4 }, { key: "warehouses", value: 4 },
  ]);
  assert.deepEqual(limitClaims("حتى 4 مستخدمين و4 فروع و4 مستودعات").map((claim) => claim.key), ["users", "branches", "warehouses"]);
  assert.deepEqual(limitClaims("Users: 1,000"), [{ key: "users", value: 1000 }]);
  assert.deepEqual(limitClaims("Unlimited branches"), [{ key: "branches", value: Infinity }]);
  assert.deepEqual(limitClaims("فروع بلا حد"), [{ key: "branches", value: Infinity }]);
  assert.deepEqual(limitClaims("24/7 priority support"), []);
});

test("the admin heuristic flags contradicting lines, not matching ones", () => {
  const plan = { modules: ["inventory", "sales"], limits: { users: 2, branches: 1 } };
  assert.deepEqual(lineProblems("Up to 2 users", plan), []);
  assert.deepEqual(lineProblems("Up to 4 users", plan), [{ kind: "limit", key: "users", claimed: 4, actual: 2 }]);
  assert.deepEqual(lineProblems("Unlimited branches", plan), [{ kind: "limit", key: "branches", claimed: null, actual: 1 }]);
  assert.deepEqual(lineProblems("Up to 3 warehouses", plan), [{ kind: "limit", key: "warehouses", claimed: 3, actual: null }]);
  assert.deepEqual(lineProblems("الموارد البشرية والرواتب", plan), [{ kind: "module", modules: ["hr"] }]);
  assert.deepEqual(lineProblems("المالية والتقارير", plan), [{ kind: "module", modules: ["finance", "reports"] }]);
  assert.deepEqual(lineProblems("Sales and purchase returns", { ...plan, modules: ["*"] }), []);
  const warnings = featureWarnings({ features_en: "Up to 4 users\nPriority support", features_ar: "حتى 4 مستخدمين", ...plan });
  assert.deepEqual(warnings.map((warning) => [warning.language, warning.key]), [["en", "users"], ["ar", "users"]]);
});

test("the compare table is built from the same plans", () => {
  const plans = normalizePlans(ROWS, "en");
  const { modules, limits } = compareMatrix(plans);
  const hr = modules.find((item) => item.code === "hr");
  assert.deepEqual(hr.cells, plans.map((plan) => plan.id === 6));
  const devices = limits.find((item) => item.key === "devices");
  assert.deepEqual(devices.cells, plans.map((plan) => (plan.id === 7 ? 2 : null)));
  assert.ok(!limits.some((item) => item.key === "storage_mb"), "no plan caps storage");
});
