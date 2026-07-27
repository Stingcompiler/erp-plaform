// Local catalogue cache so barcode scanning keeps working offline.
//
// PROJECT_RULES Rule #2 makes offline-first the default assumption for POS, but
// a barcode lookup is a network call — during an outage it would fail and stop
// the till. So the catalogue is mirrored to localStorage and scans fall back to
// it. This is a read-only convenience mirror: the server stays the source of
// truth, and nothing here is ever written back.

const KEY = "erp.productCache.v1";
const STAMP = "erp.productCache.stamp";

// Only what a scan needs to build a cart line — keeps the payload small.
function slim(p) {
  return {
    id: p.id,
    sku: p.sku,
    name: p.name,
    barcode: p.barcode || "",
    sale_price: p.sale_price,
    track_batches: p.track_batches,
  };
}

export function cacheProducts(products) {
  if (typeof window === "undefined" || !Array.isArray(products)) return;
  try {
    const withBarcodes = products.filter((p) => p && p.barcode);
    if (withBarcodes.length === 0) return;
    // Merge by barcode so paging through the catalogue accumulates rather than
    // replacing the cache with only the latest page.
    const existing = readAll();
    const merged = new Map(existing.map((p) => [p.barcode, p]));
    withBarcodes.forEach((p) => merged.set(p.barcode, slim(p)));
    window.localStorage.setItem(KEY, JSON.stringify([...merged.values()]));
    window.localStorage.setItem(STAMP, new Date().toISOString());
  } catch {
    // Quota or private-mode failures must never break the sale.
  }
}

export function readAll() {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export function findCachedByBarcode(code) {
  const target = String(code || "").trim();
  if (!target) return null;
  return readAll().find((p) => p.barcode === target) || null;
}

export function cachedAt() {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(STAMP);
  } catch {
    return null;
  }
}
