// Local mirror of the records a till needs while the server is unreachable:
// products (barcode/sku/name/price), customers, suppliers, recent invoices,
// purchase orders, bills and employees. Fed by /api/sync/pull/ (which already existed on the server but
// nothing called it) and read by the POS when a request fails.
//
// IndexedDB rather than localStorage: a catalogue of a few thousand products
// with names in two scripts is well past localStorage's ~5 MB, and IndexedDB
// reads are indexed and asynchronous, so a barcode lookup does not scan the
// whole list on the main thread. Scoped per company/user/branch like every
// other local store (see localIdentity.js), so two accounts on one machine
// never see each other's data.
//
// This is a read-only mirror. Nothing here is ever written back to the
// server; writes go through the sync queue with their own idempotency keys.

import { localScope } from "./localIdentity.js";
import { foldArabic, matchesSearch } from "./arabicFold.js";

// v2 adds purchase orders, bills and employees (receiving, paying and the
// attendance register all happen with the connection down).
const VERSION = 2;
const STORES = ["products", "warehouses", "customers", "suppliers", "invoices", "purchase_orders", "bills", "employees"];

function dbName(scope) {
  return `vezano.offline.v${VERSION}:${scope}`;
}

function open(scope = localScope()) {
  if (typeof indexedDB === "undefined") return Promise.reject(new Error("IndexedDB unavailable"));
  if (!scope) return Promise.reject(new Error("A signed-in company is required for local storage."));
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(dbName(scope), VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      for (const name of STORES) {
        if (!db.objectStoreNames.contains(name)) {
          const store = db.createObjectStore(name, { keyPath: "id" });
          if (name === "products") {
            store.createIndex("barcode", "barcode", { unique: false });
            store.createIndex("sku", "sku", { unique: false });
          }
        }
      }
      if (!db.objectStoreNames.contains("meta")) db.createObjectStore("meta", { keyPath: "key" });
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function tx(db, store, mode, work) {
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(store, mode);
    const result = work(transaction.objectStore(store));
    transaction.oncomplete = () => resolve(result?.result ?? result);
    transaction.onerror = () => reject(transaction.error);
    transaction.onabort = () => reject(transaction.error);
  });
}

function requestToPromise(request) {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

export const offlineStore = {
  async putAll(store, rows, scope) {
    if (!rows?.length) return 0;
    const db = await open(scope);
    try {
      await tx(db, store, "readwrite", (os) => { rows.forEach((row) => os.put(row)); });
      return rows.length;
    } finally { db.close(); }
  },

  async getAll(store, scope) {
    const db = await open(scope);
    try {
      return await new Promise((resolve, reject) => {
        const request = db.transaction(store).objectStore(store).getAll();
        request.onsuccess = () => resolve(request.result || []);
        request.onerror = () => reject(request.error);
      });
    } finally { db.close(); }
  },

  async count(store, scope) {
    const db = await open(scope);
    try {
      return await requestToPromise(db.transaction(store).objectStore(store).count());
    } finally { db.close(); }
  },

  async findProductByBarcode(code, scope) {
    // Arabic-Indic digits typed by hand become the ASCII the label holds.
    const target = foldArabic(String(code || "").trim());
    if (!target) return null;
    const db = await open(scope);
    try {
      const index = db.transaction("products").objectStore("products").index("barcode");
      return (await requestToPromise(index.get(target))) || null;
    } finally { db.close(); }
  },

  // Substring match on name/sku/barcode, the same fields the online search
  // hits, Arabic-folded like the server (lib/arabicFold.js) so "ارز" finds
  // "أرز" offline too. Fine for a few thousand rows; a bigger catalogue
  // would want a token index, which is not this milestone.
  async searchProducts(query, limit = 6, scope) {
    if (!String(query || "").trim()) return [];
    const rows = await this.getAll("products", scope);
    return rows
      .filter((p) => p.is_active !== false)
      .filter((p) => matchesSearch(query, [p.name, p.sku, p.barcode]))
      .slice(0, limit);
  },

  async getMeta(key, scope) {
    const db = await open(scope);
    try {
      const row = await requestToPromise(db.transaction("meta").objectStore("meta").get(key));
      return row ? row.value : null;
    } finally { db.close(); }
  },

  async setMeta(key, value, scope) {
    const db = await open(scope);
    try {
      await tx(db, "meta", "readwrite", (os) => os.put({ key, value }));
    } finally { db.close(); }
  },
};

// Pulls every change since the stored cursor into the mirror, following the
// server's page cursors, and advances the durable cursor only once the whole
// delta has landed (the server withholds `cursor` while `has_more`).
export async function pullCatalogue(syncApi, scope = localScope()) {
  if (!scope) return { pulled: 0 };
  const since = await offlineStore.getMeta("cursor", scope);
  let pageCursor = null;
  let pulled = 0;
  let cursor = since;
  for (let page = 0; page < 200; page += 1) {
    const params = pageCursor ? { page_cursor: pageCursor } : since ? { since } : {};
    const { data } = await syncApi.pull(params);
    const changes = data.changes || {};
    for (const key of Object.keys(changes)) {
      // Ledger rows (stock_movements) are not needed at the till; only the
      // stores this mirror declares are kept.
      if (!STORES.includes(key)) continue;
      pulled += await offlineStore.putAll(key, changes[key], scope);
    }
    if (!data.has_more) { cursor = data.cursor || cursor; break; }
    pageCursor = data.next_page_cursor;
  }
  if (cursor) await offlineStore.setMeta("cursor", cursor, scope);
  await offlineStore.setMeta("pulled_at", new Date().toISOString(), scope);
  return { pulled, cursor };
}

// Ask the browser not to evict this origin's storage under pressure. Best
// effort: browsers grant it silently (installed PWA, frequent use) or not at
// all, and a refusal changes nothing about how the app works.
export function requestPersistentStorage() {
  try {
    return navigator.storage?.persist?.() ?? Promise.resolve(false);
  } catch {
    return Promise.resolve(false);
  }
}
