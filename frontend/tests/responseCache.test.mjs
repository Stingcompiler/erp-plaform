import test from "node:test";
import assert from "node:assert/strict";

// Only the pure part is unit-tested; IndexedDB needs a browser.
const { cacheKey } = await import("../lib/responseCache.js");

test("GET requests are keyed by url and sorted, non-empty params", () => {
  assert.equal(cacheKey({ method: "get", url: "/debts/summary/" }), "/debts/summary/");
  assert.equal(
    cacheKey({ method: "get", url: "/reports/sales-summary/", params: { start: "2026-09-01", end: "", branch: 2 } }),
    "/reports/sales-summary/?branch=2&start=2026-09-01",
  );
  assert.equal(cacheKey({ url: "/customers/", params: { page: 1 } }), "/customers/?page=1");
});

test("writes and live-only endpoints are never cached", () => {
  assert.equal(cacheKey({ method: "post", url: "/payments/" }), null);
  assert.equal(cacheKey({ method: "get", url: "/auth/me/" }), null);
  assert.equal(cacheKey({ method: "get", url: "/health/" }), null);
  assert.equal(cacheKey({ method: "get", url: "/sync/pull/", params: { since: "x" } }), null);
  assert.equal(cacheKey({ method: "get", url: "/attention/" }), null);
  assert.equal(cacheKey({ method: "get", url: "/public/plans/" }), null);
});

test("remember/recall round-trips per scope", async () => {
  await import("fake-indexeddb/auto");
  const { remember, recall } = await import("../lib/responseCache.js");
  await remember("/debts/summary/", { outstanding: "10.00" }, "company-1");
  const hit = await recall("/debts/summary/", "company-1");
  assert.equal(hit.data.outstanding, "10.00");
  assert.ok(hit.ts > 0);
  assert.equal(await recall("/debts/summary/", "company-2"), null);
  assert.equal(await recall("/missing/", "company-1"), null);
});

test("the till's open shift and product lookups are never answered from an old copy", () => {
  assert.equal(cacheKey({ method: "get", url: "/cash-shifts/current/" }), null);
  assert.equal(cacheKey({ method: "get", url: "/products/by-barcode/", params: { code: "123" } }), null);
  assert.equal(cacheKey({ method: "get", url: "/products/", params: { search: "sugar" } }), null);
  // The plain product list (inventory page) is still remembered.
  assert.equal(cacheKey({ method: "get", url: "/products/", params: { page: 1 } }), "/products/?page=1");
});
