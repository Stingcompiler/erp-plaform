// The 2026-09-24 offline sync review: shared tablets, clocks, archived
// products, and what the till says when the server refuses a push.
import test from "node:test";
import assert from "node:assert/strict";
import "fake-indexeddb/auto";
import { IDBFactory } from "fake-indexeddb";
import { setLocalIdentity } from "../lib/localIdentity.js";
import { nextLocalReference } from "../lib/localReference.js";
import { cacheProducts, findProductOffline, searchProductsOffline } from "../lib/productCache.js";
import { offlineStore } from "../lib/offlineStore.js";
import { otherAccountsPending, queue } from "../lib/syncQueue.js";
import { clockOffset, recordServerTime } from "../lib/deviceClock.js";
import { pushErrorKind, waitingToSend } from "../lib/syncRetry.js";

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
}

test("two cashiers on one tablet never print the same provisional number", () => {
  setup();
  setLocalIdentity({ id: 1, company: 7, branch: 3 });
  const a = nextLocalReference("MAIN");
  setLocalIdentity({ id: 2, company: 7, branch: 3 });
  const b = nextLocalReference("MAIN");
  assert.notEqual(a, b);
  assert.match(a, /-000001$/);
  assert.match(b, /-000002$/);
});

test("the device counter continues from the highest old per-account counter", () => {
  setup();
  localStorage.setItem("erp.localSeq.v2:7:1:3", "41");
  localStorage.setItem("erp.localSeq.v2:7:2:3", "12");
  setLocalIdentity({ id: 2, company: 7, branch: 3 });
  assert.match(nextLocalReference("MAIN"), /-000042$/);
  assert.match(nextLocalReference("MAIN"), /-000043$/);
});

test("an archived product does not sell offline through the localStorage mirror", async () => {
  setup();
  setLocalIdentity({ id: 1, company: 7, branch: 3 });
  cacheProducts([{ id: 5, sku: "OLD", name: "Old tea", barcode: "123", sale_price: "9", is_active: true }]);
  await offlineStore.putAll("products", [{ id: 5, sku: "OLD", name: "Old tea", barcode: "123", sale_price: "9", is_active: false }], "7:1:3");
  assert.equal(await findProductOffline("123"), null);
  assert.deepEqual(await searchProductsOffline("old", 6), []);
});

test("the mirror keeps is_active, and an active product still sells from it", async () => {
  setup();
  setLocalIdentity({ id: 1, company: 7, branch: 3 });
  cacheProducts([
    { id: 6, sku: "TEA", name: "Tea", barcode: "456", sale_price: "5", is_active: true },
    { id: 7, sku: "GONE", name: "Gone tea", barcode: "789", sale_price: "5", is_active: false },
  ]);
  assert.equal((await findProductOffline("456"))?.id, 6);
  assert.equal(await findProductOffline("789"), null, "archived in the mirror itself");
});

test("each queued item carries the clock offset measured before it was captured", async () => {
  setup();
  assert.equal(clockOffset(), null);
  const sentAt = Date.parse("2026-09-24T10:00:00Z");
  // The server says 12:00 while this device thinks 10:00 (+ 1s round trip).
  recordServerTime("2026-09-24T12:00:00.500Z", sentAt, sentAt + 1000);
  assert.equal(clockOffset(), 2 * 3600 * 1000);
  const op = await queue.enqueue("pos_checkout", { amount: 10 }, "7:1:3");
  assert.equal(op.clock_offset_ms, 2 * 3600 * 1000);
  assert.equal((await queue.list("7:1:3"))[0].clock_offset_ms, 2 * 3600 * 1000);
});

test("items another account left on the device are counted", async () => {
  setup();
  await queue.enqueue("pos_checkout", { amount: 1 }, "7:1:3");
  await queue.enqueue("pos_checkout", { amount: 2 }, "7:1:3");
  await queue.enqueue("pos_checkout", { amount: 3 }, "7:2:3");
  assert.equal(await otherAccountsPending("7:2:3"), 2);
  assert.equal(await otherAccountsPending("7:1:3"), 1);
});

test("a subscription refusal is not reported as an expired session", () => {
  const refused = (status, data) => ({ response: { status, data } });
  assert.equal(pushErrorKind(refused(403, { code: "subscription_read_only", detail: "x" })), "subscription");
  assert.equal(pushErrorKind(refused(403, { code: "license_read_only" })), "subscription");
  assert.equal(pushErrorKind(refused(403, { detail: "Forbidden" })), "auth");
  assert.equal(pushErrorKind(refused(401, {})), "auth");
  assert.equal(pushErrorKind(refused(409, {})), "identity");
  assert.equal(pushErrorKind({}), "network");
});

test("only items still on their way hold an update back", () => {
  assert.equal(waitingToSend([{ error: "Refused" }, { error: null }, { attempts: 2 }]), 2);
  assert.equal(waitingToSend([{ error: "Refused" }]), 0);
  assert.equal(waitingToSend(undefined), 0);
});
