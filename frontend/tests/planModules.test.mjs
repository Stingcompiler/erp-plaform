import test from "node:test";
import assert from "node:assert/strict";
import { normalizeModules, toggleModule } from "../lib/planModules.js";

test("ticking a return pulls in what it needs; unticking a need drops the return", () => {
  assert.deepEqual(toggleModule([], "sales_returns"), ["inventory", "sales", "sales_returns"]);
  assert.deepEqual(toggleModule(["inventory", "sales", "sales_returns"], "sales"), ["inventory"]);
  assert.deepEqual(toggleModule(["inventory", "sales"], "sales"), ["inventory"]);
});

test("the API receives ['*'] for everything, else the codes in navigation order", () => {
  assert.deepEqual(normalizeModules(["*"]), ["*"]);
  assert.deepEqual(normalizeModules(["sales", "inventory", "bogus"]), ["inventory", "sales"]);
  assert.deepEqual(normalizeModules([]), []);
});
