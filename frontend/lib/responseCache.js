// "Last known" copies of read-only API responses, so the screens that are
// not part of the till (debt ledger, reports, finance, records, dashboard)
// still show something when the server is unreachable — clearly stamped as
// old, never recomputed locally.
//
// Deliberately dumb: the key is the request URL with its query string, the
// value is the JSON the server sent, plus when it was fetched. Nothing here
// derives a number the server did not; a stale figure is shown as stale
// (see StaleDataBanner), which is honest in a way a locally recalculated
// balance could not be.
//
// Scoped per company/user/branch like the other local stores, so two
// accounts on one machine never see each other's figures.

import { localScope } from "./localIdentity.js";

const VERSION = 1;
const STORE = "responses";
const MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;

// Requests that are either live-only by nature (health, auth, sync) or
// already have their own offline store (catalogue pulls). Everything else a
// screen GETs is worth remembering.
const SKIP = [
  /\/auth\//, /\/health\//, /\/sync\//, /\/attention\//, /\/ops\/preferences\//, /\/public\//,
  // The till's open drawer: a remembered answer kept a closed shift "open"
  // offline, and every sale stamped with it was refused when it synced.
  /\/cash-shifts\/current\//,
  // Barcode lookups: the synced catalogue (productCache / offlineStore) is
  // fresher than a week-old response, and a stale hit sold at an old price.
  /\/products\/by-barcode\//,
];

export function cacheKey(config) {
  if (!config || String(config.method || "get").toLowerCase() !== "get") return null;
  const url = String(config.url || "");
  if (!url || SKIP.some((re) => re.test(url))) return null;
  // A product *search* is answered offline by the synced catalogue, which
  // is fresher than a remembered search result (same reason as barcodes).
  if (/\/products\/$/.test(url) && config.params?.search) return null;
  const params = config.params
    ? Object.entries(config.params)
        .filter(([, v]) => v !== undefined && v !== null && v !== "")
        .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
        .map(([k, v]) => `${k}=${v}`)
        .join("&")
    : "";
  return params ? `${url}?${params}` : url;
}

function open(scope) {
  if (typeof indexedDB === "undefined") return Promise.reject(new Error("IndexedDB unavailable"));
  if (!scope) return Promise.reject(new Error("no scope"));
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(`vezano.responses.v${VERSION}:${scope}`, VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE, { keyPath: "key" });
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function run(db, mode, work) {
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORE, mode);
    const request = work(transaction.objectStore(STORE));
    transaction.oncomplete = () => resolve(request?.result);
    transaction.onerror = () => reject(transaction.error);
    transaction.onabort = () => reject(transaction.error);
  });
}

let pruneCounter = 0;

export async function remember(key, data, scope = localScope()) {
  try {
    const db = await open(scope);
    await run(db, "readwrite", (store) => store.put({ key, data, ts: Date.now() }));
    // Every so often drop entries nobody has refreshed in a week.
    if ((pruneCounter += 1) % 50 === 0) {
      const cutoff = Date.now() - MAX_AGE_MS;
      const all = await run(db, "readonly", (store) => store.getAll());
      await Promise.all(
        (all || []).filter((row) => row.ts < cutoff).map((row) => run(db, "readwrite", (s) => s.delete(row.key))),
      );
    }
    db.close();
  } catch {
    /* a cache is a convenience; never let it break the request */
  }
}

export async function recall(key, scope = localScope()) {
  try {
    const db = await open(scope);
    const row = await run(db, "readonly", (store) => store.get(key));
    db.close();
    return row || null;
  } catch {
    return null;
  }
}
