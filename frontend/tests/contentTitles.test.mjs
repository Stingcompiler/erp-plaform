import test from "node:test";
import assert from "node:assert/strict";
import { existsSync } from "node:fs";

import { COMPARISONS } from "../lib/content/compare.js";
import { GUIDES } from "../lib/content/guides.js";
import { SOLUTIONS } from "../lib/content/solutions.js";
import { GUIDE_TITLES, SOLUTION_TITLES } from "../lib/content/titles.js";
import { allShotFiles } from "../lib/marketingShots.js";
import { SITE_NAME, SITE_NAME_LATIN } from "../lib/site.js";

test("the footer's title list matches the articles", () => {
  const pick = (items) => items.map((item) => ({ slug: item.slug, ar: item.ar.title, en: item.en.title }));
  assert.deepEqual(SOLUTION_TITLES, pick(SOLUTIONS));
  assert.deepEqual(GUIDE_TITLES, pick(GUIDES));
});

test("every screenshot file the manifest promises exists", () => {
  const missing = allShotFiles().filter((path) => !existsSync(new URL(`../public${path}`, import.meta.url)));
  assert.deepEqual(missing, []);
});

// The SEO health check (backend/website/seo_health.py) wants the served
// <title> within 15–60 characters and the description within 50–160. Every
// content page's <title> gets the " | <brand>" suffix from the site template.
test("content pages' titles and descriptions fit the search-result limits", () => {
  const suffix = { ar: ` | ${SITE_NAME}`, en: ` | ${SITE_NAME_LATIN}` };
  const off = [];
  for (const item of [...SOLUTIONS, ...GUIDES, ...COMPARISONS]) {
    for (const language of ["ar", "en"]) {
      const copy = item[language];
      const title = (copy.metaTitle || copy.title) + suffix[language];
      if (title.length < 15 || title.length > 60) off.push(`${item.slug}/${language} title ${title.length}`);
      const length = copy.description.length;
      if (length < 50 || length > 160) off.push(`${item.slug}/${language} description ${length}`);
    }
  }
  assert.deepEqual(off, []);
});
