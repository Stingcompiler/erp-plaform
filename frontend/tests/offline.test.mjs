import test from "node:test";
import assert from "node:assert/strict";
import "fake-indexeddb/auto";
import { IDBFactory } from "fake-indexeddb";
import { queue, heldCarts } from "../lib/syncQueue.js";
import { queue as localQueue } from "../lib/syncQueueLocal.js";
import { setLocalIdentity } from "../lib/localIdentity.js";
import { cacheProducts, findCachedByBarcode } from "../lib/productCache.js";

class Storage {
  data = new Map(); fail = false;
  get length() { return this.data.size; }
  key(i) { return [...this.data.keys()][i]; }
  getItem(k) { return this.data.get(k) ?? null; }
  setItem(k, v) { if (this.fail) throw new Error("QuotaExceeded"); this.data.set(k, v); }
  removeItem(k) { this.data.delete(k); }
}
function setup() {
  globalThis.localStorage = new Storage(); globalThis.window = { localStorage };
  globalThis.indexedDB = new IDBFactory(); // a fresh, empty browser profile
}

test("partial failure retains rejected and unconfirmed sales", async () => {
  setup(); const a = await queue.enqueue("pos_checkout", {}, "1:1");
  const b = await queue.enqueue("pos_checkout", {}, "1:1");
  const c = await queue.enqueue("pos_checkout", {}, "1:1");
  await queue.acknowledge([a,b,c], [{ client_uuid: a.client_uuid, status:"applied" },
    { client_uuid: b.client_uuid, status:"error", error:"Insufficient stock" }], "1:1");
  assert.equal(await queue.count("1:1"), 2);
  assert.equal((await queue.list("1:1"))[0].error, "Insufficient stock");
  assert.ok((await queue.list("1:1"))[1].error);
  await queue.acknowledge([b], [{ client_uuid: b.client_uuid, status:"duplicate" }], "1:1");
  assert.equal(await queue.count("1:1"), 1);
});

test("retry keeps online idempotency key and never overwrites an uncertain sale", async () => {
  setup(); const id = crypto.randomUUID();
  await queue.enqueue("pos_checkout", { client_uuid: id, amount: 20 }, "1:1");
  const second = await queue.enqueue("pos_checkout", { client_uuid: id, amount: 50 }, "1:1");
  assert.equal(await queue.count("1:1"), 1);
  assert.equal((await queue.list("1:1"))[0].client_uuid, id);
  assert.equal((await queue.list("1:1"))[0].payload.amount, 20);
  assert.equal(second.payload.amount, 20, "the stored body is what a retry gets back");
});

test("company and user queues do not mix", async () => {
  setup(); await queue.enqueue("pos_checkout", {}, "1:1:1");
  assert.equal(await queue.count("2:1:1"), 0);
  assert.equal(await queue.count("1:2:1"), 0);
});

test("a cashier moved to another branch keeps the sales still waiting to upload", async () => {
  // They used to stay in the old branch's queue, never listed again: the
  // paid sales never reached the server.
  setup(); await queue.enqueue("pos_checkout", { amount: 5 }, "1:1:1");
  const rows = await queue.list("1:1:2");
  assert.equal(rows.length, 1);
  assert.equal(rows[0].payload.amount, 5);
  assert.equal(await queue.count("1:1:1"), 0); // moved, not copied
});

test("a write that does not commit rejects; a scope is required", async () => {
  setup();
  await assert.rejects(queue.enqueue("pos_checkout", {}, null));
  // Simulate the browser refusing the write: a store that throws on add.
  const original = IDBObjectStore.prototype.add;
  IDBObjectStore.prototype.add = function () { throw new Error("QuotaExceededError"); };
  try { await assert.rejects(queue.enqueue("pos_checkout", {}, "1:1")); }
  finally { IDBObjectStore.prototype.add = original; }
  assert.equal(await queue.count("1:1"), 0);
});

test("rows saved by the localStorage version migrate once, then leave localStorage", async () => {
  setup();
  const op = localQueue.enqueue("pos_checkout", { amount: 7 }, "1:1");
  localStorage.setItem("erp.syncReceipt.v2:1:1:" + "old-uuid", JSON.stringify({ id: 99, confirmed_at: 1 }));
  localStorage.setItem("erp.heldCart.v2:1:1:cart-1", JSON.stringify({ id: "cart-1", cart: [{ id: 1 }], saved_at: 5 }));
  localStorage.setItem("erp.sync.v2:1:1:broken", "not json");
  const rows = await queue.list("1:1");
  assert.equal(rows.length, 1);
  assert.equal(rows[0].client_uuid, op.client_uuid);
  assert.equal(rows[0].payload.amount, 7);
  assert.equal((await queue.confirmation("old-uuid", "1:1")).id, 99);
  assert.equal((await heldCarts.list("1:1"))[0].id, "cart-1");
  assert.equal(localStorage.getItem("erp.sync.v2:1:1:" + op.client_uuid), null, "moved out of localStorage");
  assert.equal(localStorage.getItem("erp.sync.v2:1:1:broken"), "not json", "unreadable rows are left alone");
  // A second open must not duplicate anything.
  assert.equal(await queue.count("1:1"), 1);
});

test("catalogue isolation and legacy queue quarantine", async () => {
  setup(); setLocalIdentity({id:1,company:1});
  cacheProducts([{id:1,barcode:"123",name:"Private product"}]);
  assert.equal(findCachedByBarcode("123").id, 1);
  setLocalIdentity({id:2,company:2});
  assert.equal(findCachedByBarcode("123"), null);
  setLocalIdentity(null);
  assert.equal(findCachedByBarcode("123"), null);
  localStorage.setItem("erp.sync.queue.v1", '[{"payload":{}}]');
  assert.equal(queue.hasLegacy(), true);
  assert.equal(await queue.count("2:2"), 0);
});

test("held carts retain contents and are isolated across accounts", async () => {
  setup();
  const row = await heldCarts.save({cart:[{id:7, qty:"0.25", price:"12.50"}], sale_uuid:crypto.randomUUID()}, "1:1:1");
  assert.equal((await heldCarts.list("1:1:1"))[0].cart[0].qty, "0.25");
  assert.equal((await heldCarts.list("1:2:1")).length, 0);
  await heldCarts.remove(row.id, "1:1:1");
  assert.equal((await heldCarts.list("1:1:1")).length, 0);
});

test("confirmed offline sale can resolve to its invoice without exposing another account", async () => {
  setup(); const op = await queue.enqueue("pos_checkout", {}, "1:1");
  await queue.acknowledge([op], [{client_uuid:op.client_uuid, status:"applied", id:42}], "1:1");
  assert.equal(await queue.count("1:1"), 0);
  assert.equal((await queue.confirmation(op.client_uuid, "1:1")).id, 42);
  assert.equal(await queue.confirmation(op.client_uuid, "2:1"), null);
});

test("without IndexedDB the localStorage queue still takes the sale", async () => {
  setup(); delete globalThis.indexedDB;
  const { queue: fresh } = await import("../lib/syncQueue.js?nodb");
  const op = await fresh.enqueue("pos_checkout", { amount: 3 }, "1:1");
  assert.equal(localQueue.count("1:1"), 1);
  assert.equal((await fresh.list("1:1"))[0].client_uuid, op.client_uuid);
});

test("a temporary server failure keeps the sale pending, backs off, and errors after the cap", async () => {
  setup();
  const { MAX_RETRY_ATTEMPTS, RETRY_EXHAUSTED, isDue, isRetrying } = await import("../lib/syncRetry.js");
  const op = await queue.enqueue("pos_checkout", { amount: 5 }, "1:1");
  const retry = [{ client_uuid: op.client_uuid, status: "retry", error: "try later" }];
  const before = Date.now();
  await queue.acknowledge([op], retry, "1:1");
  let [row] = await queue.list("1:1");
  assert.equal(row.error, null);
  assert.equal(row.attempts, 1);
  assert.ok(row.retry_at >= before + 30_000);
  assert.ok(isRetrying(row));
  assert.equal(isDue(row, before), false);
  assert.equal(isDue(row, row.retry_at), true);
  // The pause grows with each attempt.
  await queue.acknowledge([op], retry, "1:1");
  const [second] = await queue.list("1:1");
  assert.ok(second.retry_at - row.retry_at >= 60_000);
  for (let i = 2; i < MAX_RETRY_ATTEMPTS; i += 1) await queue.acknowledge([op], retry, "1:1");
  [row] = await queue.list("1:1");
  assert.equal(row.attempts, MAX_RETRY_ATTEMPTS);
  assert.equal(row.error, RETRY_EXHAUSTED);
  assert.equal(isRetrying(row), false);
  // A later success still clears it.
  await queue.acknowledge([op], [{ client_uuid: op.client_uuid, status: "applied", id: 7 }], "1:1");
  assert.equal(await queue.count("1:1"), 0);
});

test("the localStorage queue treats retry the same way", async () => {
  setup();
  const { MAX_RETRY_ATTEMPTS, RETRY_EXHAUSTED } = await import("../lib/syncRetry.js");
  const op = localQueue.enqueue("pos_checkout", { amount: 5 }, "1:1");
  const retry = [{ client_uuid: op.client_uuid, status: "retry" }];
  localQueue.acknowledge([op], retry, "1:1");
  let [row] = localQueue.list("1:1");
  assert.equal(row.error, null);
  assert.equal(row.attempts, 1);
  assert.ok(row.retry_at > Date.now());
  for (let i = 1; i < MAX_RETRY_ATTEMPTS; i += 1) localQueue.acknowledge([op], retry, "1:1");
  [row] = localQueue.list("1:1");
  assert.equal(row.error, RETRY_EXHAUSTED);
});
