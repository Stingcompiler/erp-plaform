import test from "node:test";
import assert from "node:assert/strict";
import { counterpartPath, localizePath, marketingLanguage } from "../lib/locale.js";

test("language is read from the URL on public pages only", () => {
  assert.equal(marketingLanguage("/"), "ar");
  assert.equal(marketingLanguage("/pricing/"), "ar");
  assert.equal(marketingLanguage("/register?plan=3"), "ar");
  assert.equal(marketingLanguage("/en"), "en");
  assert.equal(marketingLanguage("/en/"), "en");
  assert.equal(marketingLanguage("/en/product/"), "en");
  assert.equal(marketingLanguage("/en/#contact"), "en");
  assert.equal(marketingLanguage("/login/"), null);
  assert.equal(marketingLanguage("/dashboard"), null);
  assert.equal(marketingLanguage("/english/"), null);
  assert.equal(marketingLanguage(null), null);
});

test("Arabic-root hrefs gain the /en prefix in English and stay put in Arabic", () => {
  assert.equal(localizePath("/pricing", "en"), "/en/pricing");
  assert.equal(localizePath("/", "en"), "/en/");
  assert.equal(localizePath("/#contact", "en"), "/en/#contact");
  assert.equal(localizePath("/register?plan=1", "en"), "/en/register?plan=1");
  assert.equal(localizePath("/pricing", "ar"), "/pricing");
  assert.equal(localizePath("/#contact", "ar"), "/#contact");
});

test("the counterpart URL keeps query and hash", () => {
  assert.equal(counterpartPath("/en/pricing/", "ar"), "/pricing/");
  assert.equal(counterpartPath("/en/", "ar"), "/");
  assert.equal(counterpartPath("/en", "ar"), "/");
  assert.equal(counterpartPath("/register?plan=1", "en"), "/en/register?plan=1");
  assert.equal(counterpartPath("/en/#contact", "ar"), "/#contact");
  assert.equal(counterpartPath("/", "en"), "/en/");
  assert.equal(counterpartPath("/pricing/", "en"), "/en/pricing/");
});
