import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { translate } from "../lib/i18n.js";
import {
  codeLabel, filterIssueRows, isFiltered, issueCodes, issueText, overrideDraftFor, pageIssueRows, severityTone,
} from "../lib/seoHealth.js";

const ar = (key, vars) => translate("ar", key, vars);
const en = (key, vars) => translate("en", key, vars);

const PAGES = [
  {
    path: "/pricing", language: "en", url_path: "/en/pricing/", url: "https://vezano.app/en/pricing/",
    title: "Pricing", override: { id: 7, path: "/pricing", language: "en" },
    issues: [
      { code: "title_short", severity: "warn", params: { length: 7, min: 15 } },
      { code: "h1_missing", severity: "error", params: {} },
    ],
  },
  { path: "/", language: "ar", url_path: "/", url: "https://vezano.app/", title: "الرئيسية", override: null, issues: [] },
  {
    path: "/product", language: "ar", url_path: "/product/", url: "https://vezano.app/product/",
    title: "المنتج", override: null,
    issues: [{ code: "title_long", severity: "warn", params: { length: 90, max: 60 } }],
  },
];

test("one row per finding, a single ok row for a clean page, worst first", () => {
  const rows = pageIssueRows(PAGES);
  assert.deepEqual(rows.map((row) => [row.urlPath, row.code, row.severity]), [
    ["/en/pricing/", "h1_missing", "error"],
    ["/en/pricing/", "title_short", "warn"],
    ["/product/", "title_long", "warn"],
    ["/", null, "ok"],
  ]);
  assert.equal(new Set(rows.map((row) => row.key)).size, rows.length);
  assert.deepEqual(pageIssueRows(undefined), []);
});

test("filters combine severity, language, finding and text", () => {
  const rows = pageIssueRows(PAGES);
  const none = { severity: "all", language: "all", code: "all", query: "" };
  assert.equal(filterIssueRows(rows, none).length, 4);
  assert.equal(isFiltered(none), false);
  assert.deepEqual(filterIssueRows(rows, { ...none, severity: "warn" }).map((r) => r.code), ["title_short", "title_long"]);
  assert.deepEqual(filterIssueRows(rows, { ...none, language: "en" }).map((r) => r.code), ["h1_missing", "title_short"]);
  assert.deepEqual(filterIssueRows(rows, { ...none, code: "title_long" }).map((r) => r.urlPath), ["/product/"]);
  assert.deepEqual(filterIssueRows(rows, { ...none, query: "المنتج" }).map((r) => r.urlPath), ["/product/"]);
  assert.deepEqual(filterIssueRows(rows, { ...none, query: " PRICING " }).length, 2);
  assert.equal(isFiltered({ ...none, query: "x" }), true);
});

test("issue codes for the filter menu, most common first", () => {
  const rows = pageIssueRows([...PAGES, { ...PAGES[2], url_path: "/x/", path: "/x" }]);
  assert.deepEqual(issueCodes(rows), ["title_long", "h1_missing", "title_short"]);
});

test("a finding opens the override that applies, or a new one for its path and language", () => {
  const [errorRow, , longRow] = pageIssueRows(PAGES);
  assert.deepEqual(overrideDraftFor(errorRow), { id: 7, draft: null });
  assert.deepEqual(overrideDraftFor(longRow), {
    id: null,
    draft: { path: "/product", language: "ar", title: "", description: "", noindex: false, canonical: "" },
  });
});

test("severity tones match the kit's badge tones", () => {
  assert.equal(severityTone("error"), "danger");
  assert.equal(severityTone("warn"), "warn");
  assert.equal(severityTone("ok"), "ok");
});

test("findings read as sentences with their numbers, in both languages", () => {
  const issue = { code: "title_long", params: { length: 90, max: 60 } };
  assert.match(issueText(en, issue), /90.*60/);
  assert.match(issueText(ar, issue), /90.*60/);
  assert.equal(issueText(en, { code: "hreflang_missing", params: { languages: ["ar", "en"] } }), "No alternate link for: ar, en.");
  assert.equal(issueText(en, { code: null }), en("platformSeo.health.noIssues"));
  // A code this build does not know yet shows as itself, never a raw key.
  assert.equal(issueText(en, { code: "brand_new_check", params: {} }), "brand_new_check");
  assert.equal(codeLabel(en, "brand_new_check"), "brand_new_check");
  assert.equal(codeLabel(ar, "h1_missing"), "بلا h1");
});

test("every finding the backend can report is worded in Arabic and English", () => {
  const source = readFileSync(new URL("../../backend/website/seo_health.py", import.meta.url), "utf8");
  const codes = new Set([...source.matchAll(/issue\(\s*"(\w+)"/g)].map((match) => match[1]));
  for (const field of ["logo", "description", "cover", "contact", "services"]) codes.add(`company_${field}_missing`);
  for (const kind of ["title", "description"]) for (const end of ["missing", "short", "long"]) codes.add(`${kind}_${end}`);
  assert.ok(codes.size > 30, `found only ${codes.size} codes`);
  for (const code of codes) {
    for (const key of [`platformSeo.health.issues.${code}`, `platformSeo.health.codes.${code}`]) {
      assert.notEqual(en(key), key, `${key} has no wording`);
      // Arabic falls back to English when a key is missing; equal means missing.
      assert.notEqual(ar(key), en(key), `${key} has no Arabic wording`);
    }
  }
});
