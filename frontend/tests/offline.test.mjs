import test from "node:test";
import assert from "node:assert/strict";
import { queue } from "../lib/syncQueue.js";
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
function setup() { globalThis.localStorage = new Storage(); globalThis.window = { localStorage }; }
test("partial failure retains rejected and unconfirmed sales", () => {
  setup(); const a = queue.enqueue("pos_checkout", {}, "1:1");
  const b = queue.enqueue("pos_checkout", {}, "1:1");
  const c = queue.enqueue("pos_checkout", {}, "1:1");
  queue.acknowledge([a,b,c], [{ client_uuid: a.client_uuid, status:"applied" },
    { client_uuid: b.client_uuid, status:"error", error:"Insufficient stock" }], "1:1");
  assert.equal(queue.count("1:1"), 2);
  assert.equal(queue.list("1:1")[0].error, "Insufficient stock");
  assert.ok(queue.list("1:1")[1].error);
  queue.acknowledge([b], [{ client_uuid: b.client_uuid, status:"duplicate" }], "1:1");
  assert.equal(queue.count("1:1"), 1);
});
test("retry keeps online idempotency key and never overwrites an uncertain sale", () => {
  setup(); const id = crypto.randomUUID();
  queue.enqueue("pos_checkout", { client_uuid: id, amount: 20 }, "1:1");
  queue.enqueue("pos_checkout", { client_uuid: id, amount: 50 }, "1:1");
  assert.equal(queue.count("1:1"), 1);
  assert.equal(queue.list("1:1")[0].client_uuid, id);
  assert.equal(queue.list("1:1")[0].payload.amount, 20);
});
test("company, user and branch queues do not mix", () => {
  setup(); queue.enqueue("pos_checkout", {}, "1:1:1");
  assert.equal(queue.count("2:1:1"), 0);
  assert.equal(queue.count("1:2:1"), 0);
  assert.equal(queue.count("1:1:2"), 0);
});
test("storage failure propagates; corrupt data is never treated as an empty queue", () => {
  setup(); localStorage.fail = true;
  assert.throws(() => queue.enqueue("pos_checkout", {}, "1:1"));
  localStorage.fail = false;
  localStorage.setItem("erp.sync.v2:1:1:broken", "invalid");
  assert.throws(() => queue.list("1:1"));
});
test("catalogue isolation and legacy queue quarantine", () => {
  setup(); setLocalIdentity({id:1,company:1});
  cacheProducts([{id:1,barcode:"123",name:"Private product"}]);
  assert.equal(findCachedByBarcode("123").id, 1);
  setLocalIdentity({id:2,company:2});
  assert.equal(findCachedByBarcode("123"), null);
  setLocalIdentity(null);
  assert.equal(findCachedByBarcode("123"), null);
  localStorage.setItem("erp.sync.queue.v1", '[{"payload":{}}]');
  assert.equal(queue.hasLegacy(), true);
  assert.equal(queue.count("2:2"), 0);
});

test("held carts retain contents and are isolated across accounts", async () => {
  const { heldCarts } = await import("../lib/heldCarts.js");
  setup(); setLocalIdentity({id:1, company:1, branch:1});
  const row = heldCarts.save({cart:[{id:7, qty:"0.25", price:"12.50"}], sale_uuid:crypto.randomUUID()});
  assert.equal(heldCarts.list()[0].cart[0].qty, "0.25");
  setLocalIdentity({id:2, company:1, branch:1});
  assert.equal(heldCarts.list().length, 0);
  setLocalIdentity({id:1, company:1, branch:1});
  heldCarts.remove(row.id);
  assert.equal(heldCarts.list().length, 0);
});

test("confirmed offline sale can resolve to its invoice without exposing another account", () => {
  setup(); const op = queue.enqueue("pos_checkout", {}, "1:1");
  queue.acknowledge([op], [{client_uuid:op.client_uuid, status:"applied", id:42}], "1:1");
  assert.equal(queue.count("1:1"), 0);
  assert.equal(queue.confirmation(op.client_uuid, "1:1").id, 42);
  assert.equal(queue.confirmation(op.client_uuid, "2:1"), null);
});
