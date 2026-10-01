import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  ICON_TURN,
  NAV_MOTION,
  badgePops,
  bareMarketingPath,
  exitDuration,
  indicatorKeyframes,
  indicatorTransform,
  isCurrentMarketingLink,
  menuItemDelay,
  menuItemStyle,
  scrolledPast,
} from "../lib/navMotion.js";

test("every nav animation stays within 120–250 ms", () => {
  for (const key of ["indicator", "drawerIn", "drawerOut", "menuOut", "badge", "iconTurn"]) {
    assert.ok(NAV_MOTION[key] >= 120 && NAV_MOTION[key] <= 250, key);
  }
  // The last menu link starts within 125 ms, so it is in place well under 400.
  assert.ok(menuItemDelay(99) + 200 <= 350);
});

test("a header is scrolled once the page leaves the top", () => {
  assert.equal(scrolledPast(0), false);
  assert.equal(scrolledPast(4), false);
  assert.equal(scrolledPast(5), true);
  assert.equal(scrolledPast(-30), false); // an iOS bounce at the top
  assert.equal(scrolledPast(undefined), false);
  assert.equal(scrolledPast(40, 64), false);
});

test("the indicator slides only between two known places", () => {
  assert.equal(indicatorTransform(48), "translate3d(0, 48px, 0)");
  assert.equal(indicatorTransform(12.3456), "translate3d(0, 12.35px, 0)");
  assert.equal(indicatorTransform("x"), "translate3d(0, 0px, 0)");
  assert.deepEqual(indicatorKeyframes(0, 88), [
    { transform: "translate3d(0, 0px, 0)" },
    { transform: "translate3d(0, 88px, 0)" },
  ]);
  // First paint, or back from a folded group: appear in place.
  assert.equal(indicatorKeyframes(null, 88), null);
  assert.equal(indicatorKeyframes(undefined, 88), null);
  // Same place (sub-pixel noise included): nothing to slide.
  assert.equal(indicatorKeyframes(88, 88), null);
  assert.equal(indicatorKeyframes(88, 88.2), null);
  // Upwards too.
  assert.equal(indicatorKeyframes(200, 40)[1].transform, "translate3d(0, 40px, 0)");
});

test("a badge pops only for a rise after the counts first arrived", () => {
  assert.equal(badgePops(0, 3, false), false); // counts loading with the page
  assert.equal(badgePops(0, 3, true), true); // a new item while the page is open
  assert.equal(badgePops(2, 5, true), true);
  assert.equal(badgePops(5, 5, true), false);
  assert.equal(badgePops(5, 0, true), false); // opened: cleared, not popped
  assert.equal(badgePops(5, 2, true), false);
  assert.equal(badgePops(undefined, 1, true), true);
});

test("marketing paths drop the language, query, hash and trailing slash", () => {
  assert.equal(bareMarketingPath("/en/pricing/"), "/pricing");
  assert.equal(bareMarketingPath("/pricing/"), "/pricing");
  assert.equal(bareMarketingPath("/en/"), "/");
  assert.equal(bareMarketingPath("/en"), "/");
  assert.equal(bareMarketingPath("/"), "/");
  assert.equal(bareMarketingPath("/guides/x/?a=1#b"), "/guides/x");
  assert.equal(bareMarketingPath("/english-page"), "/english-page");
  assert.equal(bareMarketingPath(""), "/");
  assert.equal(bareMarketingPath(null), "/");
});

test("the header marks the page being read", () => {
  assert.equal(isCurrentMarketingLink("/pricing/", "/pricing"), true);
  assert.equal(isCurrentMarketingLink("/en/pricing/", "/pricing"), true);
  assert.equal(isCurrentMarketingLink("/en/solutions/retail/", "/solutions"), true);
  assert.equal(isCurrentMarketingLink("/guides/", "/guides"), true);
  assert.equal(isCurrentMarketingLink("/product/", "/pricing"), false);
  // A section of the home page is never "the current page".
  assert.equal(isCurrentMarketingLink("/", "/#contact"), false);
  assert.equal(isCurrentMarketingLink("/en/", "/#contact"), false);
  // No prefix match across words: /tracking is not /track.
  assert.equal(isCurrentMarketingLink("/tracking/", "/track"), false);
  assert.equal(isCurrentMarketingLink("/track/", "/track"), true);
});

test("the phone menu's stagger is short and stops growing", () => {
  assert.equal(menuItemDelay(0), 0);
  assert.equal(menuItemDelay(1), NAV_MOTION.menuStep);
  assert.equal(menuItemDelay(50), NAV_MOTION.menuStep * NAV_MOTION.menuMaxSteps);
  assert.equal(menuItemDelay(-2), 0);
  assert.equal(menuItemDelay("x"), 0);
  assert.deepEqual(menuItemStyle(2), { "--menu-delay": `${2 * NAV_MOTION.menuStep}ms` });
});

test("closing keeps nothing on screen under reduced motion", () => {
  assert.equal(exitDuration(180, false), 180);
  assert.equal(exitDuration(180, true), 0);
  assert.equal(exitDuration(undefined, false), 0);
  assert.equal(exitDuration(-5, false), 0);
});

test("a toggle's icon turns in to its resting state", () => {
  assert.equal(ICON_TURN.length, 2);
  assert.equal(ICON_TURN[1].transform, "none");
  assert.equal(ICON_TURN[1].opacity, 1);
});

// The company pages' phone tab bar is a Django template; its hide-on-scroll
// step is a pure function in the inline script, tested here as it ships.
const template = readFileSync(
  fileURLToPath(new URL("../../backend/website/templates/website/_tabbar.html", import.meta.url)),
  "utf8",
);
const source = template.match(/function tbStep\([\s\S]*?\} \/\* end tbStep \*\//)?.[0];
const tbStep = source && new Function(`${source.replace("/* end tbStep */", "")}; return tbStep;`)();
const run = (ys, start = 0) => {
  let state = { anchor: start, hidden: false };
  return ys.map((y) => (state = tbStep(state, y, 64, 48, 16)).hidden);
};

test("the tab bar's hide-on-scroll step is in the template", () => {
  assert.equal(typeof tbStep, "function");
});

test("the tab bar hides only after a real scroll down, away from the top", () => {
  // Near the top it always shows, however far the scroll ran.
  assert.deepEqual(run([20, 40, 60]), [false, false, false]);
  // Reading down: hides once 48 px past where the downward run began.
  assert.deepEqual(run([320, 340, 348, 360], 300), [false, false, true, true]);
  // A scroll up first moves where the run begins.
  assert.deepEqual(run([280, 320, 330], 300), [false, false, true]);
  // A jitter down by less than the threshold does nothing.
  assert.deepEqual(run([300, 320, 310, 330], 300), [false, false, false, false]);
});

test("the tab bar comes back on the first real scroll up", () => {
  let state = { anchor: 200, hidden: false };
  state = tbStep(state, 400, 64, 48, 16);
  assert.equal(state.hidden, true);
  // Still reading down: the anchor follows, so the way back is measured
  // from the lowest point.
  state = tbStep(state, 600, 64, 48, 16);
  assert.equal(state.anchor, 600);
  state = tbStep(state, 590, 64, 48, 16);
  assert.equal(state.hidden, true); // 10 px up: not yet
  state = tbStep(state, 584, 64, 48, 16);
  assert.equal(state.hidden, false); // 16 px up: back
  // Back at the top while hidden: shown.
  assert.equal(tbStep({ anchor: 900, hidden: true }, 10, 64, 48, 16).hidden, false);
});
