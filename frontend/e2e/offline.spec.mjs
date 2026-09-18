// The offline-first contract, end to end in a real browser:
//   open → sign in → the catalogue mirrors locally → the network goes away →
//   two sales are taken and land in IndexedDB → a reload comes back from the
//   service worker with the queue intact → the network returns → both sales
//   upload once → the server has two invoices, the stock is negative and the
//   'stock' attention badge is raised.
// Fixture: `manage.py seed_e2e` (3 units on hand; 2 + 2 sold).
import { test, expect } from "@playwright/test";

const EMAIL = "e2e-owner@vezano.test";
const PASSWORD = "E2e-owner-passw0rd!";

async function queueRows(page) {
  return page.evaluate(async () => {
    const names = (await indexedDB.databases()).map((d) => d.name).filter((n) => n.startsWith("vezano.queue.v1:"));
    const out = { ops: [], receipts: [] };
    for (const name of names) {
      const db = await new Promise((res, rej) => { const r = indexedDB.open(name); r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error); });
      for (const store of ["ops", "receipts"]) {
        const rows = await new Promise((res) => { const r = db.transaction(store).objectStore(store).getAll(); r.onsuccess = () => res(r.result); });
        out[store].push(...rows);
      }
      db.close();
    }
    return out;
  });
}

async function completeSale(page, qty) {
  const search = page.getByPlaceholder(/search a product/i);
  await search.fill("E2E");
  await page.getByRole("button", { name: /E2E Gadget/ }).first().click();
  const qtyInput = page.getByLabel(/^quantity$/i).first();
  await qtyInput.fill(String(qty));
  await page.getByRole("button", { name: /complete sale/i }).click();
  await expect(page.getByRole("heading", { name: /saved on this device/i })).toBeVisible();
  await page.getByRole("button", { name: /^new sale$/i }).click();
}

test("sales taken offline survive a reload and upload once when the network returns", async ({ page, context, request }) => {
  // The suite reads the English strings; the app defaults to Arabic.
  await context.addInitScript(() => { try { localStorage.setItem("erp.language", "en"); } catch {} });
  await page.goto("/login/");
  await page.locator("input[type=email]").fill(EMAIL);
  await page.locator("input[type=password]").fill(PASSWORD);
  await page.getByRole("button", { name: /sign in|log in/i }).click();
  await page.waitForURL(/\/dashboard\/?$/);

  // The shell worker must control the page and the catalogue must be
  // mirrored before we pull the plug — that is the state a till is in
  // after its first visit while online.
  await page.goto("/sales/");
  await expect.poll(() => page.evaluate(async () => Boolean((await navigator.serviceWorker.getRegistration())?.active))).toBe(true);
  await expect.poll(() => page.evaluate(async () => (await indexedDB.databases()).some((d) => d.name.startsWith("vezano.offline.v"))), { timeout: 30_000 }).toBe(true);
  await expect.poll(() => page.evaluate(async () => {
    const name = (await indexedDB.databases()).map((d) => d.name).find((n) => n.startsWith("vezano.offline.v"));
    const db = await new Promise((res) => { const r = indexedDB.open(name); r.onsuccess = () => res(r.result); });
    const n = await new Promise((res) => { const r = db.transaction("products").objectStore("products").count(); r.onsuccess = () => res(r.result); });
    db.close();
    return n;
  }), { timeout: 30_000 }).toBeGreaterThan(0);

  await context.setOffline(true);
  await expect(page.getByText(/working offline/i)).toBeVisible({ timeout: 40_000 });

  await completeSale(page, 2);
  await completeSale(page, 2);
  let rows = await queueRows(page);
  expect(rows.ops).toHaveLength(2);
  expect(rows.ops.every((op) => op.op_type === "pos_checkout" && op.payload.local_reference)).toBe(true);
  expect(rows.receipts).toHaveLength(0);

  // Power cut and reboot, still offline: the shell comes from the worker,
  // the session from its cache, the queue from IndexedDB.
  await page.reload();
  await expect(page.getByText(/working offline/i)).toBeVisible({ timeout: 40_000 });
  await expect(page.getByText(/2 saved locally/i)).toBeVisible();
  rows = await queueRows(page);
  expect(rows.ops).toHaveLength(2);

  await context.setOffline(false);
  await expect.poll(async () => (await queueRows(page)).ops.length, { timeout: 60_000 }).toBe(0);
  rows = await queueRows(page);
  expect(rows.receipts).toHaveLength(2);
  expect(new Set(rows.receipts.map((r) => r.id)).size).toBe(2);

  // Server side, through the same cookies the page holds.
  const cookies = (await context.cookies()).map((c) => `${c.name}=${c.value}`).join("; ");
  const headers = { Cookie: cookies };
  const invoices = await (await request.get("/api/invoices/?page_size=50", { headers })).json();
  const list = invoices.results || invoices;
  const uploaded = list.filter((inv) => rows.receipts.some((r) => r.id === inv.id));
  expect(uploaded).toHaveLength(2);
  expect(uploaded.every((inv) => /^[A-Z0-9]{1,8}-[A-Z0-9]{4}-\d{6}$/.test(inv.local_reference))).toBe(true);

  // Attention counts are cached server-side for a short while; the page
  // may have primed that cache before the upload landed, so poll past it.
  await expect.poll(async () => {
    const attention = await (await request.get("/api/attention/", { headers })).json();
    return attention.counts.stock >= 1 && attention.tones.stock === "danger";
  }, { timeout: 90_000, intervals: [2_000] }).toBe(true);
});
