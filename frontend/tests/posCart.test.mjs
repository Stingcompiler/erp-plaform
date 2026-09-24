import assert from "node:assert/strict";
import test from "node:test";

import { newTender, overDiscountLimit, paymentsFor, tenderPlan } from "../lib/posCart.js";
import { createBurstDetector } from "../lib/scanBurst.js";

const row = (method, amount, extra = {}) => ({ ...newTender(method), amount, ...extra });

test("a single blank tender pays exactly what is due", () => {
  const plan = tenderPlan([row("cash", "")], 250);
  assert.equal(plan.paid, 250);
  assert.equal(plan.change, 0);
  assert.deepEqual(paymentsFor(plan), [{ method: "cash", amount: "250" }]);
});

test("cash above the bill is change, and only the bill is recorded", () => {
  const plan = tenderPlan([row("cash", "300")], 250);
  assert.equal(plan.change, 50);
  assert.deepEqual(paymentsFor(plan), [{ method: "cash", amount: "250" }]);
});

test("cash plus Bankak: the blank row takes the rest", () => {
  const plan = tenderPlan([
    row("cash", "100"),
    row("bank_transfer", "", { bankAccount: "3", sender: " Sara ", reference: "TX1" }),
  ], 250);
  assert.equal(plan.paid, 250);
  assert.equal(plan.owed, 0);
  assert.deepEqual(paymentsFor(plan), [
    { method: "cash", amount: "100" },
    { method: "bank_transfer", amount: "150", company_bank_account: 3, sender_bank_name: "Sara", transfer_reference: "TX1" },
  ]);
});

test("a transfer above the amount due is flagged, never trimmed", () => {
  const plan = tenderPlan([row("bank_transfer", "300")], 250);
  assert.equal(plan.overTransfer, true);
  const split = tenderPlan([row("cash", "200"), row("bank_transfer", "100")], 250);
  assert.equal(split.overTransfer, false);
  assert.equal(split.cashApplied, 150);
  assert.equal(split.change, 50);
});

test("less than the bill leaves an amount owed; nothing typed as zero is a credit sale", () => {
  const plan = tenderPlan([row("cash", "100")], 250);
  assert.equal(plan.owed, 150);
  const none = tenderPlan([row("cash", "0")], 250);
  assert.deepEqual(paymentsFor(none), []);
});

test("discount limit with a cent of slack; no limit when unset", () => {
  assert.equal(overDiscountLimit(100, 10, "10"), false);
  assert.equal(overDiscountLimit(100, 10.01, "10"), false);
  assert.equal(overDiscountLimit(100, 10.5, "10"), true);
  assert.equal(overDiscountLimit(100, 90, null), false);
  assert.equal(overDiscountLimit(100, 1, "0"), true);
});

test("a price typed under the list counts toward the discount limit", () => {
  // 2 x 85 against a list of 2 x 100: 15% off, limit 10%.
  assert.equal(overDiscountLimit(170, 0, "10", 200), true);
  assert.equal(overDiscountLimit(182, 0, "10", 200), false);
  // 95 less 6% = 89.30: 10.7% under the list of 100.
  assert.equal(overDiscountLimit(95, 5.7, "10", 100), true);
  assert.equal(overDiscountLimit(95, 4.75, "10", 100), false);
  // Marked up to 120, 20% off = 96: only 4% under the list.
  assert.equal(overDiscountLimit(120, 24, "10", 100), false);
  // No list price (a miscellaneous line): the discounts alone.
  assert.equal(overDiscountLimit(100, 11, "10", 0), true);
  assert.equal(overDiscountLimit(170, 0, null, 200), false);
});

test("a scanner burst is told apart from typing", () => {
  const field = {};
  const scanner = createBurstDetector();
  "6290001234567".split("").forEach((c, i) => scanner.key(field, c, 1000 + i * 8, "2"));
  assert.deepEqual(scanner.enter(field, 1000 + 13 * 8), { code: "6290001234567", before: "2" });

  const person = createBurstDetector();
  "123456".split("").forEach((c, i) => person.key(field, c, 1000 + i * 180, ""));
  assert.equal(person.enter(field, 2200), null);

  const short = createBurstDetector();
  "12".split("").forEach((c, i) => short.key(field, c, 1000 + i * 5, ""));
  assert.equal(short.enter(field, 1012), null);
});
