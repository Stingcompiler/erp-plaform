import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { HERO, HERO_TOTAL_MS, REVEAL, headlineLines, heroEndMs, heroTiming, revealDelay } from "../lib/motion.js";
import { VIEW, branchFlowLayout, dotBegin } from "../lib/branchFlow.js";
import { homeAr, homeEn } from "../lib/marketingI18n.js";
import { HERO_ARM, HERO_GO } from "../components/landing/heroScripts.js";

test("the headline splits into whole phrases that join back into it", () => {
  for (const title of [homeAr.heroTitle, homeEn.heroTitle]) {
    const lines = headlineLines(title);
    assert.equal(lines.length, 3, title);
    assert.equal(lines.join(" "), title);
    // By the line, never by the letter: every line holds several words.
    for (const line of lines) assert.ok(line.split(/\s+/).length >= 3, line);
  }
  assert.deepEqual(headlineLines("One line only"), ["One line only"]);
  assert.deepEqual(headlineLines(""), []);
  assert.deepEqual(headlineLines(undefined), []);
});

test("the hero entrance ends within its budget", () => {
  const lines = Math.max(headlineLines(homeAr.heroTitle).length, headlineLines(homeEn.heroTitle).length);
  assert.ok(heroEndMs(lines) <= HERO_TOTAL_MS, `${heroEndMs(lines)} ms`);
  assert.ok(HERO_TOTAL_MS <= 900);
  assert.ok(HERO.fontWaitMs <= 500);
  assert.deepEqual(heroTiming("line", 2), { "--hero-delay": "140ms", "--hero-dur": "520ms" });
  assert.deepEqual(heroTiming("shot"), { "--hero-delay": "300ms", "--hero-dur": "600ms" });
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
  for (const source of [HERO_ARM, HERO_GO]) {
    assert.doesNotThrow(() => new Function(source));
    assert.ok(!source.includes("${"));
    assert.ok(!source.includes("</script"));
  }
  assert.match(HERO_ARM, /prefers-reduced-motion: reduce/);
  assert.match(HERO_ARM, /motion-ok/);
  assert.match(HERO_GO, /fonts\.load/);
  assert.match(HERO_GO, /hero-done/);
});

test("nothing is hidden unless a script armed it", () => {
  const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");
  const block = css.slice(css.indexOf("Public site motion"));
  // Every rule that sets opacity: 0 or pushes content out is keyed to an
  // armed state set from JS.
  for (const rule of block.match(/[^{}]+\{[^{}]*(opacity: 0|translateY\(calc|stroke-dashoffset: 1)[^{}]*\}/g) || []) {
    const selector = rule.slice(0, rule.indexOf("{"));
    assert.match(selector, /motion-ok|data-reveal-state="armed"|data-draw-state="armed"/, selector.trim());
  }
  assert.match(block, /prefers-reduced-motion: reduce/);
});

test("the landing page no longer ships framer-motion for its entrances", () => {
  const source = readFileSync(new URL("../components/landing/LandingPage.jsx", import.meta.url), "utf8");
  assert.ok(!source.includes("framer-motion"));
});
