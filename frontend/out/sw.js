/* Vezano app-shell service worker.
 *
 * Goal: the app OPENS without a network — after a power cut reboots the till
 * the cashier can still reach the POS and the queued sales. Data is not
 * cached here (IndexedDB owns that); this only keeps the shell available.
 *
 *   _next/static/*   cache-first   (content-hashed, immutable per build)
 *   navigations      network-first with a short timeout, then the cached page
 *   other same-origin GET assets  stale-while-revalidate
 *   /api/*           never touched
 *
 * Install is ATOMIC: every page and every asset of this build is fetched
 * into a fresh cache before the worker is allowed to install, so a shell is
 * either complete or not there. This worker never calls skipWaiting() on
 * its own: a new build waits until the page asks for it (see
 * lib/serviceWorker.js), because activating mid-session would delete the
 * cache the running page still loads chunks from — a white screen on the
 * next navigation, offline. BUILD and PRECACHE_ASSETS are stamped per build
 * by scripts/stamp-sw.mjs.
 */
const BUILD = "XChcOuWcXNFGMaiEPmlxM";
const CACHE = `vezano-shell-${BUILD}`;
// Routes a cashier needs reachable with no network at all.
const PRECACHE_PAGES = ["/", "/login/", "/dashboard/", "/sales/", "/inventory/", "/returns/"];
// Every hashed chunk, stylesheet and font of this build, plus the manifest
// and icons — filled in at build time from the export.
const PRECACHE_ASSETS = ["/_next/static/XChcOuWcXNFGMaiEPmlxM/_buildManifest.js","/_next/static/XChcOuWcXNFGMaiEPmlxM/_ssgManifest.js","/_next/static/chunks/1223-4aa069ab48298ac1.js","/_next/static/chunks/2117-9bff12b8d41d49fe.js","/_next/static/chunks/216-99b56a93902a990b.js","/_next/static/chunks/3187-b880315801d65d45.js","/_next/static/chunks/3737-3373aee40c2160ed.js","/_next/static/chunks/4307-190fcd7b2a00b6f7.js","/_next/static/chunks/5237-024d4da0cab0b659.js","/_next/static/chunks/6592-aadb95667195774a.js","/_next/static/chunks/6919-448a37df4db134eb.js","/_next/static/chunks/7303-f8fbf23017d244a5.js","/_next/static/chunks/7351-566cff9da93edb93.js","/_next/static/chunks/7958-ddb4a9b5278a6632.js","/_next/static/chunks/8058-464d3f85e0e53cde.js","/_next/static/chunks/app/(app)/crm/page-63db39cdcf48c29b.js","/_next/static/chunks/app/(app)/customer-records/page-26d3f9649c3dcdc6.js","/_next/static/chunks/app/(app)/dashboard/page-e307ee92d0f02107.js","/_next/static/chunks/app/(app)/debts/page-a92b62a2536e14da.js","/_next/static/chunks/app/(app)/finance/page-c9bec10a1c0f3d5c.js","/_next/static/chunks/app/(app)/hr/page-e739e2d22f0f8ed2.js","/_next/static/chunks/app/(app)/inventory/page-3637ff6514932207.js","/_next/static/chunks/app/(app)/labels/page-bf3183b18811322a.js","/_next/static/chunks/app/(app)/layout-f3789c5ff86ebe80.js","/_next/static/chunks/app/(app)/logs/page-8c3304f49641169c.js","/_next/static/chunks/app/(app)/org/page-1b3312216f94b1ea.js","/_next/static/chunks/app/(app)/platform-leads/page-666b1fcdebecdeb9.js","/_next/static/chunks/app/(app)/platform-plans/page-8b9ba5857ef77545.js","/_next/static/chunks/app/(app)/platform-registrations/page-cd44864651bb47f7.js","/_next/static/chunks/app/(app)/platform-subscriptions/page-a368c8cddc9338b0.js","/_next/static/chunks/app/(app)/platform-team/page-2bf13ce59a42df21.js","/_next/static/chunks/app/(app)/platform/page-7db2c5880555bc07.js","/_next/static/chunks/app/(app)/purchasing/page-5b6110f5723f25e4.js","/_next/static/chunks/app/(app)/reports/page-df308a355d587c82.js","/_next/static/chunks/app/(app)/returns/page-fb8d7ac682f0f9c4.js","/_next/static/chunks/app/(app)/sales/page-ac3b0252c520281a.js","/_next/static/chunks/app/(app)/settings/page-89932df39677d3a5.js","/_next/static/chunks/app/(app)/subscription/page-1493479bce099f6b.js","/_next/static/chunks/app/(app)/supplier-records/page-c579254b81d9d168.js","/_next/static/chunks/app/(app)/users/page-876ca731440ca0bb.js","/_next/static/chunks/app/(app)/website/page-792f1012da114666.js","/_next/static/chunks/app/_not-found/page-558c3c83ba3446b5.js","/_next/static/chunks/app/activate-owner/page-11b0930883091917.js","/_next/static/chunks/app/layout-e82daf6046cd1b0c.js","/_next/static/chunks/app/login/page-33eb0fcd7a1d963c.js","/_next/static/chunks/app/page-2da4d9ef76583664.js","/_next/static/chunks/app/pricing/page-ab146cdf1c468f2e.js","/_next/static/chunks/app/product/page-c4287ec87a52c4f7.js","/_next/static/chunks/app/register/page-9d0dba2ab7bb0c45.js","/_next/static/chunks/fd9d1056-779f51e298f418b4.js","/_next/static/chunks/framework-a63c59c368572696.js","/_next/static/chunks/main-app-6aeaabf834c73ca3.js","/_next/static/chunks/main-c4ea67350bea261d.js","/_next/static/chunks/pages/_app-78ddf957b9a9b996.js","/_next/static/chunks/pages/_error-7ce03bcf1df914ce.js","/_next/static/chunks/polyfills-42372ed130431b0a.js","/_next/static/chunks/webpack-94941dcfd14dabf9.js","/_next/static/css/2b0d5cd92e7fd4e7.css","/_next/static/css/f8ac2a9b10ec101b.css","/_next/static/media/011e180705008d6f-s.woff2","/_next/static/media/01f0c602c274ea55-s.woff2","/_next/static/media/19cfc7226ec3afaa-s.woff2","/_next/static/media/1ebb550cd0a67fc6-s.p.woff2","/_next/static/media/21350d82a1f187e9-s.woff2","/_next/static/media/350b852752f8489d-s.p.woff2","/_next/static/media/3dc379dc9b5dec12-s.p.woff2","/_next/static/media/58f386aa6b1a2a92-s.woff2","/_next/static/media/5ec84f17416dda4d-s.woff2","/_next/static/media/63a79a6cf340c5d2-s.p.woff2","/_next/static/media/7ba5fb2a8c88521c-s.woff2","/_next/static/media/8e9860b6e62d6359-s.woff2","/_next/static/media/92eeb95d069020cc-s.woff2","/_next/static/media/98e207f02528a563-s.p.woff2","/_next/static/media/99dcf268bda04fe5-s.woff2","/_next/static/media/ba9851c3c22cd980-s.woff2","/_next/static/media/c5f10e9e72d35c52-s.woff2","/_next/static/media/c5fe6dc8356a8c31-s.woff2","/_next/static/media/ce401babc0566bc1-s.woff2","/_next/static/media/d29838c109ef09b4-s.woff2","/_next/static/media/d3ebbfd689654d3a-s.p.woff2","/_next/static/media/dd994fbf464986f0-s.p.woff2","/_next/static/media/df0a9ae256c0569c-s.woff2","/_next/static/media/e40af3453d7c920a-s.woff2","/_next/static/media/e4af272ccee01ff0-s.p.woff2","/_next/static/media/e97026df054cf2a3-s.woff2","/_next/static/media/ef4d5661765d0e49-s.woff2","/_next/static/media/f15f45d13243c643-s.woff2","/icons/apple-touch-icon.png","/icons/icon-192.png","/icons/icon-512.png","/icons/icon-maskable-192.png","/icons/icon-maskable-512.png","/manifest.webmanifest"];
const NAVIGATION_TIMEOUT_MS = 3000;
// Django stamps `Vary: Accept-Language, Origin` on every response, and the
// Cache API honours Vary: a chunk stored by the worker's own fetch would
// then only match a page request carrying byte-identical Accept-Language
// and Origin headers — which a font (CORS, sends Origin) or a browser with
// a different language list never does. The shell cache is keyed by URL
// and every URL is content-hashed, so Vary carries no information here.
const MATCH = { ignoreVary: true };

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) =>
      cache.addAll([...PRECACHE_PAGES, ...PRECACHE_ASSETS].map((url) => new Request(url, { cache: "reload" }))),
    ),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))),
    ).then(() => self.clients.claim()),
  );
});

// The page decides when a waiting build may take over (queue empty, online,
// nothing on screen worth keeping).
self.addEventListener("message", (event) => {
  if (event.data?.type === "SKIP_WAITING") self.skipWaiting();
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/")) return;

  if (url.pathname.startsWith("/_next/static/")) {
    event.respondWith(cacheFirst(request));
    return;
  }
  if (request.mode === "navigate") {
    event.respondWith(networkFirst(request));
    return;
  }
  event.respondWith(staleWhileRevalidate(request));
});

async function cacheFirst(request) {
  const cache = await caches.open(CACHE);
  const hit = await cache.match(request, MATCH);
  if (hit) return hit;
  const response = await fetch(request);
  if (response.ok) cache.put(request, response.clone());
  return response;
}

// A router with no upstream — the common failure — accepts the TCP
// connection and then hangs, so "network first" without a deadline would
// keep the till staring at a blank tab for the whole browser timeout.
function fetchWithTimeout(request, ms) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), ms);
  return fetch(request, { signal: controller.signal }).finally(() => clearTimeout(timer));
}

async function networkFirst(request) {
  const cache = await caches.open(CACHE);
  try {
    const response = await fetchWithTimeout(request, NAVIGATION_TIMEOUT_MS);
    if (response.ok) cache.put(request, response.clone());
    return response;
  } catch {
    // Exact page first, then the same page with/without trailing slash, then
    // the POS as the most useful screen to land on with no network.
    const url = new URL(request.url);
    const variants = [url.pathname, url.pathname.replace(/\/?$/, "/"), "/sales/", "/dashboard/"];
    for (const path of variants) {
      const hit = await cache.match(new Request(new URL(path, url.origin)), MATCH);
      if (hit) return hit;
    }
    return new Response(
      "<!doctype html><meta charset=utf-8><title>Vezano</title>" +
      "<p style='font-family:system-ui;padding:2rem'>لا يوجد اتصال ولم تُحفظ هذه الصفحة بعد. افتح التطبيق مرة واحدة أثناء الاتصال.</p>",
      { status: 503, headers: { "Content-Type": "text/html; charset=utf-8" } },
    );
  }
}

async function staleWhileRevalidate(request) {
  const cache = await caches.open(CACHE);
  const hit = await cache.match(request, MATCH);
  const refresh = fetch(request)
    .then((response) => { if (response.ok) cache.put(request, response.clone()); return response; })
    .catch(() => null);
  return hit || (await refresh) || new Response("", { status: 504 });
}
