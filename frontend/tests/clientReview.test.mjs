import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { translate } from "../lib/i18n.js";
import { activityActionLabel, entityTypeLabel, humanizeName, metaKeyLabel, metaValueLabel } from "../lib/labels.js";
import { clearPendingLogout, flushPendingLogout, markPendingLogout, pendingLogout } from "../lib/pendingLogout.js";
import { rekeyed, sameBody } from "../lib/opBody.js";
import { clearNetworkSuspect, networkSuspect, raceNetwork } from "../lib/netRace.js";
import { overlayOpen } from "../lib/scanBurst.js";
import { CART_LIMIT_BYTES, localCarts } from "../lib/syncQueueLocal.js";

class Storage {
  data = new Map();
  get length() { return this.data.size; }
  key(i) { return [...this.data.keys()][i]; }
  getItem(k) { return this.data.get(k) ?? null; }
  setItem(k, v) { this.data.set(k, String(v)); }
  removeItem(k) { this.data.delete(k); }
}
const fresh = () => { globalThis.localStorage = new Storage(); globalThis.window = { localStorage }; };
const ar = (key, vars) => translate("ar", key, vars);
const en = (key, vars) => translate("en", key, vars);

// 1 — the identity call refreshes an expired access cookie.
test("only sign-in, refresh, sign-out and password reset skip the refresh-and-retry", () => {
  const source = readFileSync(fileURLToPath(new URL("../lib/api.js", import.meta.url)), "utf8");
  const literal = source.match(/export const NO_REFRESH_URL = (\/.*\/);/)[1];
  const re = new Function(`return ${literal}`)();
  for (const url of ["/auth/login/", "/auth/refresh/", "/auth/logout/", "/auth/password-reset/", "/auth/password-reset/confirm/"]) {
    assert.ok(re.test(url), url);
  }
  for (const url of ["/auth/me/", "/auth/change-password/", "/rbac/access/", "/sync/push/"]) {
    assert.ok(!re.test(url), url);
  }
  // Tabs share one refresh at a time and skip it when another tab just did it.
  assert.match(source, /navigator\.locks\.request\("vezano-auth-refresh"/);
  assert.match(source, /readRefreshedAt\(\) >= sentAt/);
  assert.match(source, /pendingLogout\(\)/);
});

// 2 — a sign-out the server has not heard about is kept and sent later.
test("an offline sign-out is kept until the server takes it", async () => {
  fresh();
  markPendingLogout(7);
  assert.equal(pendingLogout().user, 7);
  const offline = () => Promise.reject(Object.assign(new Error("Network Error"), { code: "ERR_NETWORK" }));
  assert.equal(await flushPendingLogout(offline), false);
  assert.ok(pendingLogout(), "still pending while offline");
  const serverDown = () => Promise.reject({ response: { status: 503 } });
  assert.equal(await flushPendingLogout(serverDown), false);
  assert.ok(pendingLogout(), "a 5xx did not clear the cookies");
  let calls = 0;
  assert.equal(await flushPendingLogout(async () => { calls += 1; }), true);
  assert.equal(pendingLogout(), null);
  assert.equal(await flushPendingLogout(async () => { calls += 1; }), true);
  assert.equal(calls, 1, "nothing pending: nothing sent");
  markPendingLogout();
  assert.equal(await flushPendingLogout(() => Promise.reject({ response: { status: 400 } })), true);
  clearPendingLogout();
});

test("the offline sign-out prompt says what really happens, in both languages", () => {
  assert.match(en("sync.signOutOffline"), /as soon as the connection returns/);
  assert.match(ar("sync.signOutOffline"), /فور عودة الاتصال/);
});

// 3 — one key, one sale.
test("a queued sale's body is compared without its times", () => {
  const a = { client_uuid: "k", occurred_at: "1", lines: [{ product: 1, quantity: "2" }] };
  assert.ok(sameBody(a, { ...a, occurred_at: "2", sent_at: "3" }));
  assert.ok(!sameBody(a, { ...a, lines: [{ product: 1, quantity: "3" }] }));
  assert.equal(rekeyed("pos_checkout", { payload: a }, { ...a, occurred_at: "9" }), null);
  const other = rekeyed("pos_checkout", { payload: a }, { ...a, lines: [] });
  assert.ok(other.client_uuid && other.client_uuid !== "k");
  assert.equal(rekeyed("payment", { payload: a }, { ...a, lines: [] }), null);
});

test("a till tab restoring a draft another tab holds gets its own key", async () => {
  const names = new Set();
  const original = Object.getOwnPropertyDescriptor(globalThis, "navigator");
  const fake = { locks: {
    request(name, options, callback) {
      if (names.has(name)) return Promise.resolve(callback(null));
      names.add(name);
      return Promise.resolve(callback({ name })).finally(() => names.delete(name));
    },
  } };
  Object.defineProperty(globalThis, "navigator", { value: fake, configurable: true, writable: true });
  const { claimSaleKey, releaseSaleKey, holdsSaleKey } = await import("../lib/saleKeys.js");
  names.add("vezano-sale:other-tab"); // held by another tab
  assert.equal(await claimSaleKey("other-tab"), false);
  assert.equal(await claimSaleKey("mine"), true);
  assert.equal(await claimSaleKey("mine"), true, "claiming again in the same tab is fine");
  assert.ok(holdsSaleKey("mine"));
  releaseSaleKey("mine");
  await new Promise((r) => setTimeout(r, 0));
  assert.ok(!names.has("vezano-sale:mine"), "released when the sale ends");
  if (original) Object.defineProperty(globalThis, "navigator", original);
  else delete globalThis.navigator;
});

// 4 — a hung network no longer freezes scanning.
test("a request that never answers is abandoned at the deadline", async () => {
  clearNetworkSuspect();
  let aborted = false;
  const started = Date.now();
  await assert.rejects(
    raceNetwork((signal) => new Promise(() => { signal?.addEventListener("abort", () => { aborted = true; }); }), { ms: 40 }),
    (err) => err.timedOut === true && !err.response,
  );
  assert.ok(Date.now() - started < 1000);
  assert.ok(aborted, "the request itself is aborted");
  assert.ok(networkSuspect(), "later lookups go to the local catalogue first");
  assert.deepEqual(await raceNetwork(async () => ({ data: 1 }), { ms: 40 }), { data: 1 });
  assert.ok(!networkSuspect(), "an answer clears the suspicion");
});

// 6 — dialogs own the keyboard.
test("an open dialog or alertdialog pauses the till's scanner capture", () => {
  const scan = { id: "scan" };
  const drawer = { contains: (el) => el === "inside" };
  const doc = (list) => ({ querySelectorAll: () => list });
  assert.equal(overlayOpen(doc([])), false);
  assert.equal(overlayOpen(doc([drawer]), scan), true);
  assert.equal(overlayOpen(doc([drawer]), "inside"), false, "a scan field inside the drawer keeps working");
});

// 8 — the activity log reads as words.
test("audit log codes, record types and metadata keys are translated", () => {
  assert.equal(activityActionLabel(ar, "device_revoked"), "إزالة جهاز");
  assert.equal(activityActionLabel(ar, "create"), "إنشاء");
  assert.equal(activityActionLabel(en, "brand_new_thing"), "Brand new thing");
  assert.equal(entityTypeLabel(ar, "StockMovement"), "حركة مخزون");
  assert.equal(entityTypeLabel(en, "FancyNewModel"), "Fancy new model");
  assert.equal(humanizeName("PurchaseOrder"), "Purchase order");
  assert.equal(metaKeyLabel(ar, "device_id"), "الجهاز");
  assert.equal(metaKeyLabel(en, "some_key"), "Some key");
  assert.equal(metaValueLabel(ar, "pos_checkout"), "بيع من نقطة البيع");
  assert.equal(metaValueLabel(en, "INV-000047"), "INV-000047");
  assert.equal(metaValueLabel(ar, true), "نعم");
});

// 10 — parked carts without IndexedDB.
test("parked carts fall back to localStorage, size-guarded", () => {
  fresh();
  localCarts.save({ id: "c1", saved_at: 1, cart: [{ id: 1 }] }, "1:1:1");
  localCarts.save({ id: "c2", saved_at: 2, cart: [{ id: 2 }] }, "1:1:1");
  assert.deepEqual(localCarts.list("1:1:1").map((r) => r.id), ["c2", "c1"]);
  assert.equal(localCarts.list("1:2:1").length, 0);
  localCarts.remove("c1", "1:1:1");
  assert.equal(localCarts.list("1:1:1").length, 1);
  assert.throws(() => localCarts.save({ id: "big", cart: "x".repeat(CART_LIMIT_BYTES) }, "1:1:1"), /too large/);
});
