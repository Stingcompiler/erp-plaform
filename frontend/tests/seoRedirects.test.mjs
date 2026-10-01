import assert from "node:assert/strict";
import test from "node:test";

import { translate } from "../lib/i18n.js";
import {
  collapsePath, draftFrom, fieldMessages, filterRedirects, importRows, isFiltered, isProtected, localErrors,
  normalizeSource, outcomeTone, sourceUrl, targetKey,
} from "../lib/seoRedirects.js";

const ar = (key, vars) => translate("ar", key, vars);
const en = (key, vars) => translate("en", key, vars);

test("sources collapse to the form the backend stores", () => {
  for (const typed of ["old-page", "/old-page", "/old-page/", " /Old-Page// ", "/old-page//"]) {
    assert.deepEqual(normalizeSource(typed), { path: "/old-page", error: null }, typed);
  }
  assert.equal(normalizeSource("/EN/Old/").path, "/en/old");
  assert.equal(normalizeSource("https://vezano.app/en/Old/").path, "/en/old");
  assert.equal(normalizeSource("//www.vezano.app/x").path, "/x");
  assert.equal(normalizeSource("/%D9%85%D8%AA%D8%AC%D8%B1/").path, "/متجر");
  assert.equal(collapsePath(""), "/");
  assert.equal(normalizeSource("").error, "sourceRequired");
  assert.equal(normalizeSource("https://example.com/x").error, "sourceHost");
  assert.equal(normalizeSource("/old?x=1").error, "sourceQuery");
  assert.equal(normalizeSource("/old#top").error, "sourceQuery");
  assert.equal(normalizeSource("/a b").error, "sourceCharacters");
  assert.equal(normalizeSource(`/${"a".repeat(300)}`).error, "sourceLong");
});

test("protected paths match the backend's list", () => {
  for (const path of [
    "/", "/en", "/s", "/api", "/api/x", "/admin", "/_next/static/a.js", "/sw.js", "/robots.txt", "/sitemap.xml",
    "/icons/i.png", "/login", "/en/login", "/dashboard", "/platform", "/platform-seo", "/platform-analytics",
    "/users/detail", "/forgot-password",
  ]) {
    assert.equal(isProtected(path), true, path);
  }
  for (const path of ["/s/shop", "/s/shop/promo", "/old-page", "/en/old", "/apiary", "/pricing", "/administration"]) {
    assert.equal(isProtected(path), false, path);
  }
});

test("targets: on-site paths and hosts, other sites only when allowed", () => {
  assert.deepEqual(targetKey("/Pricing/?a=1#x"), { key: "/pricing", external: false, error: null });
  assert.equal(targetKey("https://vezano.app/pricing/").key, "/pricing");
  assert.equal(targetKey("https://example.com/").error, "targetExternal");
  assert.deepEqual(targetKey("https://example.com/", true), { key: null, external: true, error: null });
  assert.equal(targetKey("").error, "targetRequired");
  assert.equal(targetKey("//example.com").error, "targetDoubleSlash");
  assert.equal(targetKey("http://vezano.app/").error, "targetScheme");
  assert.equal(targetKey("pricing").error, "targetScheme");
  assert.equal(targetKey("https://u:p@vezano.app/").error, "targetCredentials");
  assert.equal(targetKey("/a b").error, "targetCharacters");
});

test("the form's instant rules", () => {
  assert.deepEqual(localErrors({ source_path: "/old", target: "/pricing/", status_code: 301 }), { source: "/old", errors: {} });
  assert.deepEqual(localErrors({ source_path: "/login", target: "/pricing/", status_code: 301 }).errors, { source_path: "sourceProtected" });
  assert.deepEqual(localErrors({ source_path: "/Old/", target: "/old", status_code: 302 }).errors, { target: "targetSelf" });
  assert.deepEqual(localErrors({ source_path: "/old", target: "https://x.example/", status_code: 301 }).errors, { target: "targetExternal" });
  assert.deepEqual(localErrors({ source_path: "/old", target: "https://x.example/", status_code: 301, allow_external: true }).errors, {});
  assert.deepEqual(localErrors({ source_path: "/old", target: "/new", status_code: 303 }).errors, { status_code: "status" });
});

test("every instant error and outcome is worded in both languages", () => {
  const keys = [
    "sourceRequired", "sourceHost", "sourceQuery", "sourceCharacters", "sourceLong", "sourceProtected", "targetRequired",
    "targetLong", "targetCharacters", "targetDoubleSlash", "targetScheme", "targetCredentials", "targetExternal",
    "targetSelf", "status",
  ].map((code) => `platformSeo.redirects.errors.${code}`);
  keys.push(...["redirect", "none", "protected", "inactive", "invalid"].map((code) => `platformSeo.redirects.outcomes.${code}`));
  keys.push("platformSeo.tabRedirects", "platformSeo.redirects.title", "platformSeo.health.redirectsTitle");
  for (const key of keys) {
    assert.notEqual(en(key), key, `${key} has no wording`);
    assert.notEqual(ar(key), en(key), `${key} has no Arabic wording`);
  }
});

const ROWS = [
  { id: 1, source_path: "/old-pricing", target: "/pricing/", note: "renamed", is_active: true },
  { id: 2, source_path: "/s/old-shop", target: "/s/new-shop/", note: "", is_active: false },
  { id: 3, source_path: "/blog", target: "https://blog.example.com/", note: "Blog moved", is_active: true },
];

test("search and the active filter combine", () => {
  const none = { query: "", state: "all" };
  assert.equal(filterRedirects(ROWS, none).length, 3);
  assert.equal(isFiltered(none), false);
  assert.deepEqual(filterRedirects(ROWS, { ...none, state: "active" }).map((r) => r.id), [1, 3]);
  assert.deepEqual(filterRedirects(ROWS, { ...none, state: "inactive" }).map((r) => r.id), [2]);
  assert.deepEqual(filterRedirects(ROWS, { ...none, query: " SHOP " }).map((r) => r.id), [2]);
  assert.deepEqual(filterRedirects(ROWS, { ...none, query: "blog moved" }).map((r) => r.id), [3]);
  assert.deepEqual(filterRedirects(ROWS, { query: "pricing", state: "inactive" }), []);
  assert.equal(isFiltered({ query: "", state: "active" }), true);
  assert.deepEqual(filterRedirects(undefined), []);
});

test("drafts, server messages, outcomes and import rows", () => {
  assert.deepEqual(draftFrom(null), { source_path: "", target: "", status_code: 301, is_active: true, allow_external: false, note: "" });
  assert.deepEqual(draftFrom({ ...ROWS[0], status_code: "302", allow_external: false, hits: 5 }), {
    source_path: "/old-pricing", target: "/pricing/", status_code: 302, is_active: true, allow_external: false, note: "renamed",
  });
  assert.deepEqual(fieldMessages({ target: ["Chain."], source_path: "Taken." }), { target: "Chain.", source_path: "Taken." });
  assert.deepEqual(fieldMessages(undefined), {});
  assert.equal(outcomeTone("redirect"), "ok");
  assert.equal(outcomeTone("invalid"), "danger");
  assert.equal(outcomeTone("whatever"), "muted");
  assert.equal(sourceUrl("/old"), "https://vezano.app/old/");
  assert.equal(sourceUrl("/"), "https://vezano.app/");
  const rows = importRows({
    rows: [
      { line: 2, errors: {} },
      { line: 3, errors: { target: "Bad." } },
      { line: 4, errors: { source_path: "Taken.", target: "Bad." } },
    ],
  });
  assert.deepEqual(rows.map((row) => [row.line, row.messages.length]), [[3, 1], [4, 2], [2, 0]]);
  assert.deepEqual(importRows(null), []);
});
