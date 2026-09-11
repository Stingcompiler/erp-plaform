import test from "node:test";
import assert from "node:assert/strict";
import { visibleNav } from "../components/nav.js";
const flatten = (items) => items.flatMap((i) => i.children || [i]).map((i) => i.href);
test("shop optional sections restore only permitted routes", () => {
  const read = (m) => !m || ["sales","inventory"].includes(m);
  const write = (m) => m === "inventory";
  assert.ok(!flatten(visibleNav(read,write,"Sales Officer","shop")).includes("/labels"));
  const routes = flatten(visibleNav(read,write,"Sales Officer","shop",["nav.labels","nav.customerRecords","nav.hr"]));
  assert.ok(routes.includes("/labels"));
  assert.ok(routes.includes("/customer-records"));
  assert.ok(!routes.includes("/hr"));
});
