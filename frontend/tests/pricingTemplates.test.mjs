import assert from "node:assert/strict";
import test from "node:test";

import {
  billingCycles,
  DEFAULT_DISPLAY,
  featuredOrder,
  formatPlanAmount,
  normalizePlans,
  offerRows,
  planOffers,
  PRICING_TEMPLATES,
  resolveCycle,
  resolveDisplay,
} from "../lib/planCatalog.js";
import { currencyLabel, isPlanCurrency, PLAN_CURRENCIES } from "../lib/money.js";

// A plan sold monthly (v3, id 31) and yearly (v4, id 40, newest); one sold
// monthly only; one yearly only.
const row = (id, extra = {}) => ({
  id,
  plan_code: `code-${id}`,
  plan_name: `plan ${id}`,
  currency: "SDG",
  price: "1000.00",
  billing_cycle: "monthly",
  trial_days: 14,
  modules: ["inventory", "sales"],
  limits: { users: 3 },
  ...extra,
  display: { name: { en: `Plan ${id}`, ar: `باقة ${id}` }, sort_order: 100, is_highlighted: false, ...extra.display },
});
const BOTH = row(40, {
  price: "10000.00",
  billing_cycle: "yearly",
  limits: { users: 5 },
  display: { sort_order: 10, is_highlighted: true },
  cycles: {
    monthly: { id: 31, currency: "SDG", price: "1000.00", billing_cycle: "monthly", modules: ["inventory", "sales"], limits: { users: 3 } },
    yearly: { id: 40, currency: "SDG", price: "10000.00", billing_cycle: "yearly", modules: ["inventory", "sales"], limits: { users: 5 } },
  },
});
const MONTHLY_ONLY = row(50, { price: "2000.00", display: { sort_order: 20 }, cycles: { monthly: { id: 50, currency: "SDG", price: "2000.00", billing_cycle: "monthly", modules: [], limits: {} } } });
const YEARLY_ONLY = row(60, { price: "30000.00", billing_cycle: "yearly", display: { sort_order: 30 } });

test("offers: the row is always the offer for its own cycle; older rows without `cycles` work", () => {
  assert.deepEqual(Object.keys(planOffers(BOTH)).sort(), ["monthly", "yearly"]);
  assert.equal(planOffers(BOTH).monthly.id, 31);
  assert.deepEqual(Object.keys(planOffers(YEARLY_ONLY)), ["yearly"]);
  assert.equal(planOffers(YEARLY_ONLY).yearly.id, 60);
});

test("the switch shows only when a plan really has both cycles", () => {
  assert.deepEqual(billingCycles([BOTH, MONTHLY_ONLY]), ["monthly", "yearly"]);
  // Monthly on one plan and yearly on another is not a choice for anyone.
  assert.deepEqual(billingCycles([MONTHLY_ONLY, YEARLY_ONLY]), []);
  assert.deepEqual(billingCycles([]), []);
  assert.deepEqual(billingCycles(null), []);
});

test("cycle choice: remembered, else the platform default, else the first", () => {
  const both = ["monthly", "yearly"];
  assert.equal(resolveCycle(both, "yearly", "monthly"), "yearly");
  assert.equal(resolveCycle(both, null, "yearly"), "yearly");
  assert.equal(resolveCycle(both, "weekly", "nonsense"), "monthly");
  assert.equal(resolveCycle([], "yearly", "yearly"), null);
});

test("a chosen cycle uses that cycle's real version; a missing one is unavailable, not invented", () => {
  const yearly = normalizePlans([BOTH, MONTHLY_ONLY, YEARLY_ONLY], "en", {}, { cycle: "yearly" });
  const [both, monthlyOnly, yearlyOnly] = yearly;
  assert.equal(both.id, 40);
  assert.deepEqual(both.price, { kind: "paid", amount: 10000, currency: "SDG" });
  assert.equal(both.cycle, "yearly");
  assert.deepEqual(both.limits, { users: 5 });
  assert.equal(monthlyOnly.available, false);
  assert.deepEqual(monthlyOnly.price, { kind: "unavailable" });
  assert.deepEqual(monthlyOnly.offeredCycles, ["monthly"]);
  assert.equal(yearlyOnly.available, true);

  const monthly = normalizePlans([BOTH, MONTHLY_ONLY, YEARLY_ONLY], "en", {}, { cycle: "monthly" });
  assert.equal(monthly[0].id, 31, "the monthly version is what a sign-up requests");
  assert.equal(monthly[0].price.amount, 1000);
  assert.deepEqual(monthly[0].limits, { users: 3 });
  assert.equal(monthly[2].available, false);
  // The same plans in the same order, whatever the cycle; keys stay stable.
  assert.deepEqual(monthly.map((plan) => plan.key), yearly.map((plan) => plan.key));
  assert.deepEqual(monthly.map((plan) => plan.key), [40, 50, 60]);
  // Nothing is ever derived: no amount that is not a published price.
  const amounts = [...monthly, ...yearly].filter((plan) => plan.price.kind === "paid").map((plan) => plan.price.amount);
  assert.deepEqual([...new Set(amounts)].sort((a, b) => a - b), [1000, 2000, 10000, 30000]);
});

test("without a switch each plan shows the cycle it is sold on", () => {
  const plans = normalizePlans([MONTHLY_ONLY, YEARLY_ONLY], "en");
  assert.deepEqual(plans.map((plan) => [plan.cycle, plan.available]), [["monthly", true], ["yearly", true]]);
});

test("the sign-up list has one option per real offer", () => {
  const offers = offerRows([BOTH, MONTHLY_ONLY, YEARLY_ONLY]);
  assert.deepEqual(offers.map((offer) => [offer.id, offer.billing_cycle]), [[31, "monthly"], [40, "yearly"], [50, "monthly"], [60, "yearly"]]);
  assert.equal(offers[0].display.name.en, "Plan 40", "an offer keeps the plan's copy");
  assert.equal(offers[0].price, "1000.00");
});

test("template selection: only known templates; anything else is the classic default", () => {
  assert.deepEqual(PRICING_TEMPLATES, ["classic", "featured", "table", "compact"]);
  assert.deepEqual(resolveDisplay(null), DEFAULT_DISPLAY);
  assert.deepEqual(resolveDisplay({ template: "carousel", show_compare: "yes", default_cycle: "weekly" }), DEFAULT_DISPLAY);
  for (const template of PRICING_TEMPLATES) assert.equal(resolveDisplay({ template }).template, template);
  assert.deepEqual(
    resolveDisplay({ template: "table", show_compare: false, show_self_hosted: false, default_cycle: "yearly" }),
    { template: "table", show_compare: false, show_self_hosted: false, default_cycle: "yearly" },
  );
});

test("featured: the highlighted plan goes in the middle, others keep their order", () => {
  const plan = (id, highlighted = false) => ({ id, highlighted });
  assert.deepEqual(featuredOrder([plan(1, true), plan(2), plan(3)]).map((p) => p.id), [2, 1, 3]);
  assert.deepEqual(featuredOrder([plan(1), plan(2), plan(3), plan(4, true)]).map((p) => p.id), [1, 2, 4, 3]);
  assert.deepEqual(featuredOrder([plan(1), plan(2, true)]).map((p) => p.id), [1, 2]);
  assert.deepEqual(featuredOrder([plan(1), plan(2)]).map((p) => p.id), [1, 2], "no badge: order untouched");
});

test("plan currencies: a small ISO set; an unknown code still reads as itself", () => {
  assert.ok(PLAN_CURRENCIES.includes("SDG") && PLAN_CURRENCIES.includes("USD"));
  for (const code of PLAN_CURRENCIES) assert.match(code, /^[A-Z]{3}$/);
  assert.equal(isPlanCurrency("SDG"), true);
  assert.equal(isPlanCurrency("sdg"), true);
  assert.equal(isPlanCurrency("SD"), false);
  assert.equal(isPlanCurrency(""), false);
  assert.equal(currencyLabel("XYZ", "ar"), "XYZ");
  assert.equal(formatPlanAmount(1500, "XYZ", "en"), "1,500 XYZ");
  const [plan] = normalizePlans([row(1, { currency: "XYZ" })], "ar");
  assert.deepEqual(plan.price, { kind: "paid", amount: 1000, currency: "XYZ" });
});
