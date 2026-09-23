import assert from "node:assert/strict";
import test from "node:test";

import { round2 } from "../lib/money.js";

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
