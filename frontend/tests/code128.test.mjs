import assert from "node:assert/strict";
import test from "node:test";

import { PATTERNS, code128Svg, code128Symbols } from "../lib/code128.js";

test("the symbol table is the standard one in shape", () => {
  assert.equal(PATTERNS.length, 107);
  assert.equal(new Set(PATTERNS).size, 107);
  PATTERNS.forEach((p, value) => {
    const widths = [...p].map(Number);
    const total = widths.reduce((a, b) => a + b, 0);
    assert.equal(total, value === 106 ? 13 : 11, `symbol ${value}`);
    // Code 128 parity: the bars of every symbol add up to an even number.
    const barsOnly = widths.filter((_, i) => i % 2 === 0).reduce((a, b) => a + b, 0);
    assert.equal(barsOnly % 2, 0, `symbol ${value} parity`);
  });
});

test("set B for text, with the weighted mod-103 check symbol", () => {
  // Start B 104; P=48 J=42 J=42 1=17 2=18 3=19 C=35.
  // 104 + 48*1 + 42*2 + 42*3 + 17*4 + 18*5 + 19*6 + 35*7 = 879 -> 879 % 103 = 55.
  assert.deepEqual(code128Symbols("PJJ123C"), [104, 48, 42, 42, 17, 18, 19, 35, 55, 106]);
});

test("set C packs even-length digits in pairs", () => {
  // 105 + 62*1 + 90*2 + 0*3 + 2*4 = 355 -> 355 % 103 = 46.
  assert.deepEqual(code128Symbols("62900002"), [105, 62, 90, 0, 2, 46, 106]);
  // An odd last digit goes through Code B: "123" = C, 12, CodeB, "3"(19).
  // 105 + 12*1 + 100*2 + 19*3 = 374 -> 374 % 103 = 65.
  assert.deepEqual(code128Symbols("123"), [105, 12, 100, 19, 65, 106]);
  assert.equal(code128Symbols("6290000000002").length, 11);
});

test("unprintable input draws nothing", () => {
  assert.equal(code128Symbols(""), null);
  assert.equal(code128Svg("سكر"), "");
  assert.match(code128Svg("A-102"), /^<svg /);
});
