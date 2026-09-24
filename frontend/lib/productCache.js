// Local catalogue cache so barcode scanning keeps working offline.
//
// PROJECT_RULES Rule #2 makes offline-first the default assumption for POS, but
// a barcode lookup is a network call — during an outage it would fail and stop
// the till. So the catalogue is mirrored to localStorage and scans fall back to
// it. This is a read-only convenience mirror: the server stays the source of
// truth, and nothing here is ever written back.

import { localScope, storageKey } from "./localIdentity.js";
import { offlineStore } from "./offlineStore.js";

// Only what a scan needs to build a cart line — keeps the payload small.
function slim(p) {
  return {
    id: p.id,
    sku: p.sku,
    name: p.name,
    barcode: p.barcode || "",
    sale_price: p.sale_price,
    track_batches: p.track_batches,
    unit_name: p.unit_name,
    is_stock_tracked: p.is_stock_tracked,
    // Warning inputs for the till; stale offline, but a stale warning beats none.
    on_hand: p.on_hand,
    expiry_status: p.expiry_status,
  };
}

export function cacheProducts(products) {
  if (typeof window === "undefined" || !Array.isArray(products) || !localScope()) return;
  try {
    const withBarcodes = products.filter((p) => p && p.barcode);
    if (withBarcodes.length === 0) return;
    // Merge by barcode so paging through the catalogue accumulates rather than
    // replacing the cache with only the latest page.
    const existing = readAll();
    const merged = new Map(existing.map((p) => [p.barcode, p]));
    withBarcodes.forEach((p) => merged.set(p.barcode, slim(p)));
    window.localStorage.setItem(storageKey("productCache"), JSON.stringify([...merged.values()]));
    window.localStorage.setItem(storageKey("productCacheStamp"), new Date().toISOString());
  } catch {
    // Quota or private-mode failures must never break the sale.
  }
}

export function readAll() {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(storageKey("productCache"));
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
    return window.localStorage.getItem(storageKey("productCacheStamp"));
  } catch {
    return null;
  }
}

// Full offline lookup: the IndexedDB mirror (fed by sync/pull, covers the
// whole catalogue) first, then the localStorage mirror of what this browser
// has seen (still useful before the first pull completes).
// An archived product is not for sale, online or off.
const sellable = (p) => (p && p.is_active !== false ? p : null);

export async function findProductOffline(code) {
  try {
    const hit = sellable(await offlineStore.findProductByBarcode(code));
    if (hit) return hit;
  } catch { /* no IndexedDB / no scope: fall through */ }
  return sellable(findCachedByBarcode(code));
}

export async function searchProductsOffline(query, limit = 6) {
  try {
    const hits = (await offlineStore.searchProducts(query, limit * 2)).filter(sellable).slice(0, limit);
    if (hits.length) return hits;
  } catch { /* fall through */ }
  const needle = String(query || "").toLowerCase();
  return readAll().filter((p) => sellable(p) && `${p.name} ${p.sku}`.toLowerCase().includes(needle)).slice(0, limit);
}
