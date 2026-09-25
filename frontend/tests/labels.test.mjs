import assert from "node:assert/strict";
import test from "node:test";

import { translate } from "../lib/i18n.js";
import {
  activityActionLabel, enumLabel, humanize, invoiceStatusLabel, paymentMethodLabel,
  subscriptionStateLabel,
} from "../lib/labels.js";
import { isEmptyReport, planIncludes, slotFromError } from "../lib/reportSlots.js";

const ar = (key, vars) => translate("ar", key, vars);
const en = (key, vars) => translate("en", key, vars);

test("every invoice status reads as words in both languages", () => {
  for (const status of ["issued", "partially_paid", "paid", "void"]) {
    for (const t of [ar, en]) {
      const label = invoiceStatusLabel(t, status);
      assert.notEqual(label, status);
      assert.doesNotMatch(label, /_/);
    }
  }
  assert.equal(invoiceStatusLabel(ar, "partially_paid"), "مسددة جزئيًا");
  assert.equal(invoiceStatusLabel(en, "paid"), "Paid");
});

test("an unknown code is humanized, never shown raw", () => {
  assert.equal(humanize("partially_paid"), "Partially paid");
  assert.equal(enumLabel(en, "labels.invoiceStatus", "on_hold"), "On hold");
  assert.equal(enumLabel(en, "labels.invoiceStatus", null), "—");
});

test("payment methods: codes and the documents' English display both translate", () => {
  assert.equal(paymentMethodLabel(ar, "bank_transfer"), "تحويل بنكي");
  assert.equal(paymentMethodLabel(ar, "Bank Transfer"), "تحويل بنكي");
  assert.equal(paymentMethodLabel(ar, "Store credit"), "رصيد متجر");
  assert.equal(paymentMethodLabel(ar, "Cash"), "نقدًا");
});

test("subscription states and activity actions use the existing catalog", () => {
  assert.equal(subscriptionStateLabel(ar, "trialing"), "تجريبي");
  assert.equal(activityActionLabel(ar, "create"), "إنشاء");
  assert.equal(activityActionLabel(en, "mystery_step"), "Mystery step");
});

test("report slots tell a failure from a refusal from an empty period", () => {
  assert.equal(slotFromError({ response: { status: 403, data: { code: "module_not_in_plan" } } }), "locked");
  assert.equal(slotFromError({ response: { status: 403, data: {} } }), "forbidden");
  assert.equal(slotFromError({ response: { status: 500 } }), "error");
  assert.equal(slotFromError({}), "error");
  assert.equal(isEmptyReport([]), true);
  assert.equal(isEmptyReport({ rows: [] }), true);
  assert.equal(isEmptyReport({ items: [{}] }), false);
  assert.equal(isEmptyReport({ totals: { total: "0" } }), false);
});

test("planIncludes reads the /me entitlements list", () => {
  assert.equal(planIncludes({ modules: ["sales", "inventory"] }, "reports"), false);
  assert.equal(planIncludes({ modules: ["*"] }, "reports"), true);
  assert.equal(planIncludes({ modules: ["reports"] }, "reports"), true);
  assert.equal(planIncludes({}, "reports"), true);
  assert.equal(planIncludes(null, "reports"), true);
});

test("the new state strings exist in both languages", () => {
  for (const key of ["states.reportFailed", "states.reportsNotInPlanTitle", "states.awaitingSummary", "states.inventoryProductsTab"]) {
    assert.notEqual(ar(key), key);
    assert.notEqual(en(key), key);
    assert.notEqual(ar(key), en(key));
  }
});
