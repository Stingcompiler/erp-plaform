import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { HERO, HERO_START_OPACITY, HERO_TOTAL_MS, REVEAL, heroEndMs, heroTiming, revealDelay } from "../lib/motion.js";
import { VIEW, branchFlowLayout, dotBegin } from "../lib/branchFlow.js";
import { homeAr, homeEn } from "../lib/marketingI18n.js";
import { HERO_ARM } from "../components/landing/heroScripts.js";

test("the headline is one short message, the modules are in the subtitle", () => {
  assert.equal(homeAr.heroTitle, "إدارة متكاملة لشركتك وفروعها. والبيع يستمر عند انقطاع الشبكة.");
  assert.equal(homeEn.heroTitle, "Manage your company and branches together. Keep selling through outages.");
  assert.match(homeAr.heroSubtitle, /المخزون/);
  assert.match(homeEn.heroSubtitle, /inventory/);
});

test("the hero entrance never hides anything and ends within its budget", () => {
  assert.ok(heroEndMs() <= HERO_TOTAL_MS, `${heroEndMs()} ms`);
  assert.ok(HERO_TOTAL_MS <= 600);
  assert.ok(HERO_START_OPACITY >= 0.4);
  assert.ok(!("line" in HERO), "the headline has no entrance");
  assert.deepEqual(heroTiming("shot"), { "--hero-delay": "120ms", "--hero-dur": "480ms" });
});

test("the h1 has no motion rule and no wrapper that could hide it", () => {
  const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");
  assert.ok(!/hero-mask|hero-rise|h1/.test(css.slice(css.indexOf("Public site motion"), css.indexOf("Section cards (lib/useRevealOnce.js)")).replace(/\/\*[\s\S]*?\*\//g, "")));
  const source = readFileSync(new URL("../components/landing/LandingPage.jsx", import.meta.url), "utf8");
  const h1 = source.slice(source.indexOf("<h1"), source.indexOf("</h1>"));
  assert.ok(!/hero-|style=|<span/.test(h1), h1);
  const keyframes = css.match(/@keyframes hero-[a-z]+ \{[^}]*\}/g) || [];
  assert.ok(keyframes.length >= 2);
  for (const rule of keyframes) assert.match(rule, /opacity: 0\.4/, rule);
});

test("section cards stagger a little and stop growing", () => {
  assert.equal(revealDelay(0), 0);
  assert.equal(revealDelay(1), REVEAL.step);
  assert.equal(revealDelay(50), REVEAL.step * REVEAL.maxSteps);
  assert.equal(revealDelay(-3), 0);
  assert.ok(REVEAL.duration <= 250);
  assert.ok(REVEAL.duration + revealDelay(99) <= 450);
});

test("the branch diagram mirrors for Arabic and stays inside its box", () => {
  const ltr = branchFlowLayout("ltr");
  const rtl = branchFlowLayout("rtl");
  assert.equal(ltr.branches.length, 3);
  // The first branch is where the reader starts: left in English, right in Arabic.
  assert.ok(ltr.branches[0].x < ltr.branches[2].x);
  ltr.branches.forEach((branch, index) => assert.equal(rtl.branches[index].x, VIEW.width - branch.x));
  ltr.tiles.forEach((tile, index) => {
    assert.equal(rtl.tiles[index].x + tile.width, VIEW.width - tile.x);
    assert.equal(rtl.tiles[index].tone, tile.tone);
  });
  // Checkerboard like the logo.
  assert.deepEqual(ltr.tiles.map((tile) => tile.tone), ["solid", "pale", "pale", "solid"]);
  for (const layout of [ltr, rtl]) {
    for (const branch of layout.branches) {
      const numbers = branch.path.match(/-?\d+(\.\d+)?/g).map(Number);
      const [x0, y0] = numbers;
      const [x1, y1] = numbers.slice(-2);
      assert.equal(x0, branch.x);
      assert.equal(y0, branch.y + branch.height / 2);
      assert.equal(y1, layout.hub.y, "every path lands on the hub's top edge");
      assert.ok(x1 >= layout.hub.x && x1 <= layout.hub.x + layout.hub.width);
      assert.ok(branch.x - branch.width / 2 >= 0 && branch.x + branch.width / 2 <= VIEW.width);
    }
    assert.ok(layout.caption.y < VIEW.height);
  }
  assert.equal(dotBegin(0), "0.9s");
  assert.equal(dotBegin(2), "2.5s");
});

test("the diagram's copy exists in both languages", () => {
  for (const copy of [homeAr, homeEn]) {
    assert.equal(copy.flowBranches.length, 3);
    assert.equal(copy.flowModules.length, 4);
    assert.ok(copy.flowHub && copy.flowLabel.length > 40);
  }
  assert.deepEqual(homeAr.flowBranches, ["الخرطوم", "أم درمان", "بحري"]);
  assert.deepEqual(homeEn.flowBranches, ["Khartoum", "Omdurman", "Bahri"]);
});

test("the hero's inline scripts are valid, self-contained and honour reduced motion", () => {
  assert.doesNotThrow(() => new Function(HERO_ARM));
  assert.ok(!HERO_ARM.includes("${"));
  assert.ok(!HERO_ARM.includes("</script"));
  assert.match(HERO_ARM, /prefers-reduced-motion: reduce/);
  assert.match(HERO_ARM, /motion-ok/);
  assert.match(HERO_ARM, /hero-done/);
  // No wait for a font: nothing in the hero is held back.
  assert.ok(!/fonts/.test(HERO_ARM));
});

test("nothing is hidden unless a script armed it", () => {
  const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");
  const block = css.slice(css.indexOf("Public site motion"));
  // Every rule that sets opacity: 0 or pushes content out is keyed to an
  // armed state set from JS.
  for (const rule of block.match(/[^{}]+\{[^{}]*(opacity: 0[;\s}]|translateY\(calc|stroke-dashoffset: 1)[^{}]*\}/g) || []) {
    const selector = rule.slice(0, rule.indexOf("{"));
    assert.match(selector, /motion-ok|data-reveal-state="armed"|data-draw-state="armed"/, selector.trim());
  }
  assert.match(block, /prefers-reduced-motion: reduce/);
});

test("the landing page no longer ships framer-motion for its entrances", () => {
  const source = readFileSync(new URL("../components/landing/LandingPage.jsx", import.meta.url), "utf8");
  assert.ok(!source.includes("framer-motion"));
});
