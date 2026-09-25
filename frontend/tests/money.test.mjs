import assert from "node:assert/strict";
import test from "node:test";

import { currencyLabel, formatAmount, formatMoney, round2 } from "../lib/money.js";

test("half-up like the server's Decimal rounding", () => {
  assert.equal(round2(10.075), 10.08); // Math.round(n*100)/100 gives 10.07
  assert.equal(round2(1.005), 1.01);
  assert.equal(round2(2.675), 2.68);
  assert.equal(round2(0.125), 0.13);
});

test("ordinary values and negatives", () => {
  assert.equal(round2(5), 5);
  assert.equal(round2(4.994), 4.99);
  assert.equal(round2(-1.005), -1.01);
  assert.equal(round2("3.335"), 3.34);
  assert.equal(round2(undefined), 0);
});

// One display rule for money (identity review 2026-09-25): two decimals,
// grouped, Latin digits; "ج.س" in Arabic and "SDG" in English.
test("formatAmount: two decimals, grouping, Latin digits, server rounding", () => {
  assert.equal(formatAmount(1234.5), "1,234.50");
  assert.equal(formatAmount("8.4"), "8.40");
  assert.equal(formatAmount(10.075), "10.08");
  assert.equal(formatAmount(-0.001), "0.00");
  assert.equal(formatAmount(-1500), "-1,500.00");
  assert.equal(formatAmount(null), "0.00");
  assert.equal(formatAmount(null, { empty: "—" }), "—");
  assert.equal(formatAmount("", { empty: "—" }), "—");
  assert.equal(formatAmount("abc", { empty: "—" }), "—");
  assert.match(formatAmount(1234567.891), /^[0-9,.]+$/);
});

test("currencyLabel: every spelling of the Sudanese pound reads the same", () => {
  for (const code of ["SDG", "SD", "sdg", " SDD ", "ج.س"]) {
    assert.equal(currencyLabel(code, "ar"), "ج.س");
    assert.equal(currencyLabel(code, "en"), "SDG");
  }
  assert.equal(currencyLabel("USD", "en"), "USD");
  assert.equal(currencyLabel("USD", "ar"), "دولار");
  assert.equal(currencyLabel("XYZ", "ar"), "XYZ");
  assert.equal(currencyLabel("", "ar"), "");
});

test("formatMoney: figure then label; a missing figure stays a dash", () => {
  assert.equal(formatMoney(8.4, { currency: "SDG", language: "ar" }), "8.40 ج.س");
  assert.equal(formatMoney(8.4, { currency: "SD", language: "en" }), "8.40 SDG");
  assert.equal(formatMoney(200000, { currency: "SD", language: "ar" }), "200,000.00 ج.س");
  assert.equal(formatMoney(5, {}), "5.00");
  assert.equal(formatMoney(undefined, { currency: "SDG", language: "ar", empty: "—" }), "—");
});
