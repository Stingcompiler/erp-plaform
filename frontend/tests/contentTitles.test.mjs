import test from "node:test";
import assert from "node:assert/strict";
import { existsSync } from "node:fs";

import { GUIDES } from "../lib/content/guides.js";
import { SOLUTIONS } from "../lib/content/solutions.js";
import { GUIDE_TITLES, SOLUTION_TITLES } from "../lib/content/titles.js";
import { allShotFiles } from "../lib/marketingShots.js";

test("the footer's title list matches the articles", () => {
  const pick = (items) => items.map((item) => ({ slug: item.slug, ar: item.ar.title, en: item.en.title }));
  assert.deepEqual(SOLUTION_TITLES, pick(SOLUTIONS));
  assert.deepEqual(GUIDE_TITLES, pick(GUIDES));
});

test("every screenshot file the manifest promises exists", () => {
  const missing = allShotFiles().filter((path) => !existsSync(new URL(`../public${path}`, import.meta.url)));
  assert.deepEqual(missing, []);
});
