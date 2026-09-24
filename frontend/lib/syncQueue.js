// The durable queue: sales and other writes taken while the server was
// unreachable, plus the receipts that confirm them and the carts a cashier
// parked. One IndexedDB database per company/user/branch scope.
//
// Why IndexedDB and not localStorage (where this lived until P3): browsers
// treat localStorage as disposable — Safari clears it after seven days
// without use, Chromium under disk pressure — and it is the one store that
// cannot be covered by navigator.storage.persist(). IndexedDB can, and it
// gives real transactions, so two tabs cannot half-write each other's rows.
//
// Rules carried over unchanged from the localStorage version:
//   * a failed write MUST throw — the caller keeps the sale on screen;
//   * re-enqueueing a client_uuid keeps the ORIGINAL body (an uncertain
//     network request retried must not change what was sent);
//   * an unreadable row is an error, never silently an empty queue.
//
// If IndexedDB itself is unavailable (some private modes) the old
// localStorage implementation is used so a sale is still never dropped.
// Rows found in localStorage from before this version are migrated into
// IndexedDB the first time the scope is opened.

import { localScope, storageKey } from "./localIdentity.js";
import { queue as localQueue } from "./syncQueueLocal.js";
import { retryPatch } from "./syncRetry.js";

const VERSION = 1;
const DB_PREFIX = "vezano.queue.v1:";
const STORES = { ops: "client_uuid", receipts: "client_uuid", carts: "id" };

function open(scope) {
  if (!scope) return Promise.reject(new Error("A signed-in company is required for local storage."));
  if (typeof indexedDB === "undefined") return Promise.reject(new Error("IndexedDB unavailable"));
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_PREFIX + scope, VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      for (const [name, keyPath] of Object.entries(STORES)) {
        if (!db.objectStoreNames.contains(name)) {
          const store = db.createObjectStore(name, { keyPath });
          if (name === "ops") store.createIndex("queued_at", "queued_at");
          if (name === "carts") store.createIndex("saved_at", "saved_at");
        }
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error("IndexedDB open failed"));
    request.onblocked = () => reject(new Error("IndexedDB blocked"));
  });
}

// Runs `work(store)` in one transaction and resolves when it has COMMITTED,
// which is the only moment a write is actually durable.
async function withStore(scope, name, mode, work) {
  const db = await open(scope);
  try {
    return await new Promise((resolve, reject) => {
      const transaction = db.transaction(name, mode);
      const store = transaction.objectStore(name);
      let result;
      try { result = work(store); } catch (err) { reject(err); transaction.abort?.(); return; }
      // `work` may hand back an IDBRequest (unwrap its result — which can
      // legitimately be undefined), a promise, or a plain value.
      const isRequest = result && typeof result === "object" && "readyState" in result && "result" in result;
      transaction.oncomplete = () => resolve(isRequest ? result.result : result);
      transaction.onerror = () => reject(transaction.error || new Error("IndexedDB transaction failed"));
      transaction.onabort = () => reject(transaction.error || new Error("IndexedDB transaction aborted"));
    });
  } finally { db.close(); }
}

const req = (r) => new Promise((resolve, reject) => { r.onsuccess = () => resolve(r.result); r.onerror = () => reject(r.error); });

async function getAll(scope, name) {
  return withStore(scope, name, "readonly", (store) => store.getAll());
}

function validOp(row) {
  return row && typeof row === "object" && row.client_uuid && row.payload && typeof row.payload === "object";
}

// Whether IndexedDB works here; decided once per page and remembered so a
// scope never straddles two backends.
let backend = null;
async function indexedDbWorks(scope) {
  if (backend !== null) return backend;
  try { (await open(scope)).close(); backend = true; }
  catch { backend = false; }
  return backend;
}

// Copy this scope's rows out of localStorage (the pre-P3 layout) into
// IndexedDB, deleting each localStorage row only after its IndexedDB
// transaction committed. Safe to run on every open: it is a no-op once
// nothing is left. A legacy row that will not parse is left in place and
// reported by hasLegacy()/list() exactly as before.
async function migrateFromLocalStorage(scope) {
  if (typeof localStorage === "undefined") return 0;
  let moved = 0;
  const move = async (prefix, store, shape) => {
    const keys = [];
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key?.startsWith(prefix)) keys.push(key);
    }
    for (const key of keys) {
      let row;
      try { row = shape(JSON.parse(localStorage.getItem(key)), key.slice(prefix.length)); } catch { continue; }
      if (!row) continue;
      await withStore(scope, store, "readwrite", (os) => { os.put(row); });
      localStorage.removeItem(key);
      moved += 1;
    }
  };
  await move(`${storageKey("sync", scope)}:`, "ops", (row) => (validOp(row) ? row : null));
  await move(`${storageKey("syncReceipt", scope)}:`, "receipts", (row, id) => (row?.id ? { client_uuid: id, ...row } : null));
  await move(`${storageKey("heldCart", scope)}:`, "carts", (row) => (row?.id ? row : null));
  return moved;
}

// The scope includes the branch, so when an admin moves a cashier to another
// branch the next sign-in opens a different, empty queue — and the sales
// still waiting in the old one were never sent, never shown, never
// discarded: gone. Anything this same person left under another branch of
// this company is moved into the current queue (the server still applies
// its own branch rules to each operation) and the old database is deleted
// only after the copy has committed.
const siblingsDone = new Set();
function siblingPrefix(scope) {
  const [company, user] = String(scope).split(":");
  return company && user ? `${DB_PREFIX}${company}:${user}:` : null;
}
async function adoptSiblingQueues(scope) {
  if (siblingsDone.has(scope)) return 0;
  siblingsDone.add(scope);
  const prefix = siblingPrefix(scope);
  if (!prefix || typeof indexedDB?.databases !== "function") return 0;
  let moved = 0;
  const others = (await indexedDB.databases())
    .map((d) => d.name)
    .filter((name) => name && name.startsWith(prefix) && name !== DB_PREFIX + scope);
  for (const name of others) {
    const oldScope = name.slice(DB_PREFIX.length);
    const [ops, carts] = [await getAll(oldScope, "ops"), await getAll(oldScope, "carts")];
    const rows = ops.filter(validOp);
    if (rows.length || carts.length) {
      await withStore(scope, "ops", "readwrite", (store) => { rows.forEach((row) => store.put(row)); });
      await withStore(scope, "carts", "readwrite", (store) => { carts.forEach((row) => store.put(row)); });
      moved += rows.length;
    }
    await new Promise((resolve) => {
      const request = indexedDB.deleteDatabase(name);
      request.onsuccess = request.onerror = request.onblocked = () => resolve();
    });
  }
  return moved;
}

// Migration runs on every open: it is a prefix scan of localStorage keys,
// cheap, and a no-op once nothing is left — so nothing in memory can get
// out of step with what is actually still in localStorage.
async function ready(scope) {
  if (!(await indexedDbWorks(scope))) return false;
  try { await migrateFromLocalStorage(scope); }
  catch { throw new Error("Could not move saved operations to durable storage."); }
  try { await adoptSiblingQueues(scope); }
  catch { /* the old queue stays where it is and is tried again next page */ siblingsDone.delete(scope); }
  return true;
}

// Two sales queued within the same millisecond still upload in the order
// they were taken.
let seq = 0;
const byQueueOrder = (a, b) => (a.queued_at - b.queued_at) || ((a.seq || 0) - (b.seq || 0));

export const queue = {
  async list(scope) {
    if (!(await ready(scope))) return localQueue.list(scope);
    const rows = await getAll(scope, "ops");
    for (const row of rows) if (!validOp(row)) throw new Error("Invalid saved operation.");
    return rows.sort(byQueueOrder);
  },

  async count(scope) {
    return (await this.list(scope)).length;
  },

  // Rows from the pre-scope layout (v1) that cannot be attributed to an
  // account. Synchronous: it only inspects localStorage.
  hasLegacy: () => localQueue.hasLegacy(),

  async enqueue(opType, payload, scope) {
    if (!(await ready(scope))) return localQueue.enqueue(opType, payload, scope);
    const id = payload.client_uuid || crypto.randomUUID();
    const op = { op_type: opType, client_uuid: id,
      payload: { ...payload, client_uuid: id }, queued_at: Date.now(), seq: ++seq, error: null };
    // add() (not put) refuses to overwrite: a retry of an uncertain request
    // keeps the original body, and the stored one is what is returned.
    return withStore(scope, "ops", "readwrite", (store) => new Promise((resolve, reject) => {
      const get = store.get(id);
      get.onsuccess = () => {
        if (get.result) { resolve(get.result); return; }
        const add = store.add(op);
        add.onsuccess = () => resolve(op);
        add.onerror = () => reject(add.error);
      };
      get.onerror = () => reject(get.error);
    }));
  },

  async confirmation(id, scope) {
    if (!(await ready(scope))) return localQueue.confirmation(id, scope);
    try {
      const row = await withStore(scope, "receipts", "readonly", (store) => store.get(id));
      return row ? { id: row.id, confirmed_at: row.confirmed_at } : null;
    } catch { return null; }
  },

  // Repair a refused operation in place (e.g. attach the customer a sale on
  // account needs) and clear its error so the next sync sends it again.
  // client_uuid is kept, so the server still sees one sale, not two.
  async amend(id, patch, scope) {
    if (!(await ready(scope))) return localQueue.amend(id, patch, scope);
    return withStore(scope, "ops", "readwrite", (store) => new Promise((resolve, reject) => {
      const get = store.get(id);
      get.onsuccess = () => {
        if (!get.result) { resolve(null); return; }
        const next = { ...get.result, payload: { ...get.result.payload, ...patch },
          error: null, error_field: null, attempts: 0, retry_at: null };
        const put = store.put(next);
        put.onsuccess = () => resolve(next);
        put.onerror = () => reject(put.error);
      };
      get.onerror = () => reject(get.error);
    }));
  },

  async acknowledge(sent, results, scope) {
    if (!Array.isArray(results)) throw new Error("Missing synchronization results.");
    if (!(await ready(scope))) return localQueue.acknowledge(sent, results, scope);
    const accepted = new Map(results.map((r) => [r.client_uuid, r]));
    const db = await open(scope);
    try {
      await new Promise((resolve, reject) => {
        const transaction = db.transaction(["ops", "receipts"], "readwrite");
        const ops = transaction.objectStore("ops");
        const receipts = transaction.objectStore("receipts");
        for (const op of sent) {
          const result = accepted.get(op.client_uuid);
          if (result?.status === "applied" || result?.status === "duplicate" || result?.status === "discarded") {
            if (op.op_type === "pos_checkout" && result.id) {
              receipts.put({ client_uuid: op.client_uuid, id: result.id, confirmed_at: Date.now() });
            }
            ops.delete(op.client_uuid);
          } else if (result?.status === "retry") {
            // A temporary failure on the server: still pending, sent again
            // after a pause (see syncRetry.js), an error only after the cap.
            const get = ops.get(op.client_uuid);
            get.onsuccess = () => {
              if (get.result) ops.put({ ...get.result, ...retryPatch(get.result) });
            };
          } else {
            const get = ops.get(op.client_uuid);
            get.onsuccess = () => {
              if (get.result) ops.put({ ...get.result, error: result?.error || "__no_confirmation__", error_field: result?.error_field || null });
            };
          }
        }
        transaction.oncomplete = resolve;
        transaction.onerror = () => reject(transaction.error);
        transaction.onabort = () => reject(transaction.error);
      });
    } finally { db.close(); }
  },
};

// Parked carts, same database. `scope` defaults to the active identity.
export const heldCarts = {
  async list(scope = localScope()) {
    if (!(await ready(scope))) throw new Error("Durable storage unavailable.");
    return (await getAll(scope, "carts")).sort((a, b) => b.saved_at - a.saved_at);
  },
  async save(cart, scope = localScope()) {
    const row = { ...cart, id: cart.id || crypto.randomUUID(), saved_at: Date.now() };
    if (!(await ready(scope))) throw new Error("Durable storage unavailable.");
    await withStore(scope, "carts", "readwrite", (store) => { store.put(row); });
    return row;
  },
  async remove(id, scope = localScope()) {
    if (!id) return;
    if (!(await ready(scope))) return;
    await withStore(scope, "carts", "readwrite", (store) => { store.delete(id); });
  },
};

// Rough headroom check so the drawer can warn before a sale fails to save.
export async function storageHeadroom() {
  try {
    const { usage = 0, quota = 0 } = (await navigator.storage?.estimate?.()) || {};
    if (!quota) return null;
    return { usage, quota, low: quota - usage < 50 * 1024 * 1024 || usage / quota > 0.9 };
  } catch { return null; }
}


