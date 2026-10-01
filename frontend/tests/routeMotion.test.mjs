import assert from "node:assert/strict";
import test from "node:test";

import {
  ENTER,
  ROUTE_ENTER,
  countChange,
  enterDelay,
  enterStyle,
  routeEnterApplies,
  routeEnterKeyframes,
} from "../lib/motion.js";

test("the route entrance plays between two different app pages", () => {
  assert.equal(routeEnterApplies("/dashboard", "/subscription"), true);
  assert.equal(routeEnterApplies("/inventory/", "/finance/"), true);
  assert.equal(routeEnterApplies("/sales", "/dashboard"), true);
});

test("no entrance on first paint or for the same page", () => {
  assert.equal(routeEnterApplies(null, "/dashboard"), false);
  assert.equal(routeEnterApplies(undefined, "/dashboard"), false);
  assert.equal(routeEnterApplies("", "/dashboard"), false);
  assert.equal(routeEnterApplies("/dashboard", "/dashboard"), false);
  // The export uses trailing slashes; the same page with and without is one.
  assert.equal(routeEnterApplies("/dashboard", "/dashboard/"), false);
});

test("nothing moves on arrival at the till", () => {
  assert.equal(routeEnterApplies("/dashboard", "/sales"), false);
  assert.equal(routeEnterApplies("/dashboard", "/sales/"), false);
  assert.equal(routeEnterApplies("/dashboard", "/sales/anything"), false);
  // A route that merely starts with the same letters is not the till.
  assert.equal(routeEnterApplies("/dashboard", "/sales-report"), true);
});

test("the entrance is a short fade and rise that ends at rest", () => {
  assert.ok(ROUTE_ENTER.duration >= 150 && ROUTE_ENTER.duration <= 200);
  assert.ok(ROUTE_ENTER.distance >= 6 && ROUTE_ENTER.distance <= 8);
  const [from, to] = routeEnterKeyframes();
  assert.equal(from.opacity, 0);
  assert.equal(from.transform, `translateY(${ROUTE_ENTER.distance}px)`);
  assert.deepEqual(to, { opacity: 1, transform: "none" });
});

test("card entrances stagger and stop growing", () => {
  assert.equal(enterDelay(0), 0);
  assert.equal(enterDelay(1), ENTER.step);
  assert.equal(enterDelay(ENTER.maxSteps), ENTER.maxSteps * ENTER.step);
  assert.equal(enterDelay(40), ENTER.maxSteps * ENTER.step);
  assert.equal(enterDelay(-3), 0);
  assert.equal(enterDelay("x"), 0);
  assert.ok(ENTER.duration <= 250);
  assert.deepEqual(enterStyle(2), { "--enter-delay": `${2 * ENTER.step}ms` });
});

test("a value counts as changed only between two known values", () => {
  let state = { value: undefined, count: 0 };
  state = countChange(state, "Pro"); // first load
  assert.deepEqual(state, { value: "Pro", count: 0 });
  state = countChange(state, "Pro");
  assert.equal(state.count, 0);
  state = countChange(state, "Enterprise");
  assert.deepEqual(state, { value: "Enterprise", count: 1 });
  state = countChange(state, null); // gone (reloading)
  assert.equal(state.count, 1);
  state = countChange(state, "Enterprise");
  assert.equal(state.count, 1);
  state = countChange(state, "grace");
  assert.equal(state.count, 2);
});
