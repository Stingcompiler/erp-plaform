// The offline search folds Arabic exactly like the server (core/arabic.py).
import test from "node:test";
import assert from "node:assert/strict";
import "fake-indexeddb/auto";
import { IDBFactory } from "fake-indexeddb";
import { foldArabic, matchesSearch } from "../lib/arabicFold.js";
import { setLocalIdentity } from "../lib/localIdentity.js";
import { cacheProducts, findProductOffline, searchProductsOffline } from "../lib/productCache.js";
import { offlineStore } from "../lib/offlineStore.js";

class Storage {
  data = new Map();
  get length() { return this.data.size; }
  key(i) { return [...this.data.keys()][i]; }
  getItem(k) { return this.data.get(k) ?? null; }
  setItem(k, v) { this.data.set(k, String(v)); }
  removeItem(k) { this.data.delete(k); }
}
function setup() {
  globalThis.localStorage = new Storage(); globalThis.window = { localStorage };
  globalThis.indexedDB = new IDBFactory();
  setLocalIdentity({ id: 1, company: 7, branch: 3 });
}

test("the fold matches the server's fold_arabic", () => {
  // Same case as backend sales/test_pos_review.py SearchTests.test_fold.
  assert.equal(foldArabic("أَرُزّ إ آ ة ى ـ ٣"), "ارز ا ا ه ي  3");
  assert.equal(foldArabic("ٱلؤلؤ مائدة"), "الولو مايده");
  assert.equal(foldArabic("ًْٰ"), "");
  assert.equal(foldArabic("٠١٢٣٤٥٦٧٨٩ ۰۱۲۳۴۵۶۷۸۹"), "0123456789 0123456789");
  assert.equal(foldArabic("Rice-5kg"), "Rice-5kg");
  assert.equal(foldArabic(null), "");
});

test("every term must match a field, ignoring Arabic variants and Latin case", () => {
  const fields = ["أرز بسمتي", "RICE", "6290001"];
  for (const q of ["أرز", "ارز", "بسمتى", "ارز بسمتى", "rice", "٦٢٩", "rice ارز"]) {
    assert.ok(matchesSearch(q, fields), q);
  }
  assert.ok(!matchesSearch("سكر", fields));
  assert.ok(!matchesSearch("ارز سكر", fields));
  assert.ok(!matchesSearch("   ", fields));
});

test("the IndexedDB mirror is searched in folded form", async () => {
  setup();
  await offlineStore.putAll("products", [
    { id: 1, sku: "RICE", name: "أرز بسمتي", barcode: "6290001", sale_price: "100", is_active: true },
    { id: 2, sku: "SUG", name: "سكر", barcode: "", sale_price: "50", is_active: true },
  ], "7:1:3");
  assert.deepEqual((await searchProductsOffline("ارز بسمتى")).map((p) => p.id), [1]);
  assert.deepEqual((await searchProductsOffline("٦٢٩٠٠")).map((p) => p.id), [1]);
  assert.equal((await findProductOffline("٦٢٩٠٠٠١"))?.id, 1);
});

test("the localStorage mirror is searched in folded form", async () => {
  setup();
  cacheProducts([{ id: 3, sku: "OIL", name: "زيت ذُرة", barcode: "777", sale_price: "9", is_active: true }]);
  assert.deepEqual((await searchProductsOffline("زيت ذره")).map((p) => p.id), [3]);
  assert.deepEqual((await searchProductsOffline("٧٧٧")).map((p) => p.id), [3]);
  assert.equal((await findProductOffline("٧٧٧"))?.id, 3);
});
