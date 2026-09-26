import assert from "node:assert/strict";
import test from "node:test";

import { figureChars, figureFitStyle, splitFigure } from "../lib/figureFit.js";
import { formatMoney } from "../lib/money.js";

test("a figure's width counts Latin/digits as one cell, Arabic letters wider", () => {
  // 10 digits/punctuation + space + ج (1.75) . (1) س (1.75)
  assert.equal(figureChars("615,480.00 ج.س"), 15.5);
  assert.equal(figureChars(formatMoney(12615480, { currency: "SDG" })), 18.5);
  assert.equal(figureChars(formatMoney(615480, { currency: "SDG", language: "en" })), 14);
  assert.equal(figureChars("1,025.80 SDG"), 12);
});

test("the Arabic label never makes a figure narrower than its English twin", () => {
  for (const value of [0, 12.5, 1025.8, 615480, 12615480]) {
    const ar = figureChars(formatMoney(value, { currency: "SDG", language: "ar" }));
    const en = figureChars(formatMoney(value, { currency: "SDG", language: "en" }));
    assert.ok(ar >= en, `${value}: ${ar} < ${en}`);
  }
});

test("a money figure splits into number and label; nothing else splits", () => {
  assert.deepEqual(splitFigure("615,480.00 ج.س"), ["615,480.00", "ج.س"]);
  assert.deepEqual(splitFigure(formatMoney(-1234.5, { currency: "SDG", language: "en" })),
    ["-1,234.50", "SDG"]);
  assert.deepEqual(splitFigure(formatMoney(12, { currency: "USD" })), ["12.00", "دولار"]);
  assert.equal(splitFigure("0.00"), null);
  assert.equal(splitFigure("منشور"), null);
  assert.equal(splitFigure("45%"), null);
  assert.equal(splitFigure("3 نشطة · 1 تجربة"), null);
  assert.equal(splitFigure(60), null);
  assert.equal(splitFigure(null), null);
});

test("short figures and missing values keep the tier's full size", () => {
  assert.equal(figureChars("3"), 6);
  assert.equal(figureChars("—"), 6);
  assert.equal(figureChars(null), 6);
  assert.equal(figureChars(undefined), 6);
  assert.equal(figureChars(42), 6);
});

test("Arabic combining marks take no width", () => {
  assert.equal(figureChars("جُنَيْه سُودانِي"), figureChars("جنيه سوداني"));
});

test("longer figures ask for a smaller size", () => {
  const short = figureFitStyle(formatMoney(1025.8, { currency: "SDG" }))["--figure-chars"];
  const long = figureFitStyle(formatMoney(615480, { currency: "SDG" }))["--figure-chars"];
  assert.ok(long > short);
});
