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
const BUILD = "24IRTM4dPHU1FbZSy4aEQ";
const CACHE = `vezano-shell-${BUILD}`;
// Every screen of the app, so the person lands on the page they asked for
// with no network — never on a different one. Filled in at build time from
// the export; the list below is the floor the PWA manifest relies on.
const PRECACHE_PAGES = ["/", "/login/", "/dashboard/", "/sales/", "/inventory/", "/returns/"];
const PRECACHE_APP_PAGES = ["/activate-owner/","/crm/","/customer-records/","/dashboard/","/debts/","/finance/","/forgot-password/","/hr/","/inventory/","/labels/","/login/","/logs/","/org/","/platform-activity/","/platform-analytics/","/platform-companies/","/platform-errors/","/platform-finance/","/platform-leads/","/platform-plans/","/platform-registrations/","/platform-seo/","/platform-subscriptions/","/platform-team/","/platform-team/member/","/platform/","/purchasing/","/reports/","/reset-password/","/returns/","/sales/","/settings/","/subscription/","/supplier-records/","/users/","/users/detail/","/web-orders/","/website/"];
// Every hashed chunk, stylesheet and font of this build, plus the manifest
// and icons — filled in at build time from the export.
const PRECACHE_ASSETS = ["/_next/static/24IRTM4dPHU1FbZSy4aEQ/_buildManifest.js","/_next/static/24IRTM4dPHU1FbZSy4aEQ/_ssgManifest.js","/_next/static/chunks/1247-ab70fb6a06523bfb.js","/_next/static/chunks/2017-2b5a50fa5ca16968.js","/_next/static/chunks/2218-d514cff52506fbad.js","/_next/static/chunks/2549-095286aa79aa569c.js","/_next/static/chunks/2841.86f35ccd294715ef.js","/_next/static/chunks/3406-f621011b15624d63.js","/_next/static/chunks/3569-0a151bf8ea9af3f4.js","/_next/static/chunks/3727-248d422872eeec32.js","/_next/static/chunks/3922-44254cb46b81fb04.js","/_next/static/chunks/4877-b602a8c028bd43ad.js","/_next/static/chunks/5024-50a836c1f87eb7c6.js","/_next/static/chunks/5258-ff9059770b6d0d54.js","/_next/static/chunks/5291-3e2900b2152ea36e.js","/_next/static/chunks/5308-cab963b28151265f.js","/_next/static/chunks/5949-3313b2c3627f3a61.js","/_next/static/chunks/5959-2a566bc00a7f1db5.js","/_next/static/chunks/6712-6a7fcf8a1d63025b.js","/_next/static/chunks/7069-7f85b156a990a93f.js","/_next/static/chunks/719-662217eb3165b1b3.js","/_next/static/chunks/7359-40945d5211d1152d.js","/_next/static/chunks/7566-5fae5d85a95b5737.js","/_next/static/chunks/802-21edc8cac76b8de7.js","/_next/static/chunks/8039-4cb1ced102b37c7e.js","/_next/static/chunks/8170-3b2073dea992214d.js","/_next/static/chunks/8558-ef7a7c56ea3ae526.js","/_next/static/chunks/8605-50879c729dfd959b.js","/_next/static/chunks/9272-f9f3d4b4bf78f0b1.js","/_next/static/chunks/9301-0e619f79735e3c18.js","/_next/static/chunks/9899-18dcf26cdd2226c6.js","/_next/static/chunks/app/(app)/crm/page-f95566627483ad61.js","/_next/static/chunks/app/(app)/customer-records/page-a87e845dca9a1708.js","/_next/static/chunks/app/(app)/dashboard/page-a29c4e9f03d05084.js","/_next/static/chunks/app/(app)/debts/page-774c794351ea1cd6.js","/_next/static/chunks/app/(app)/finance/page-987560efb510c4b5.js","/_next/static/chunks/app/(app)/hr/page-72960cbf0301bbb8.js","/_next/static/chunks/app/(app)/inventory/page-6df7eb6b120a3c48.js","/_next/static/chunks/app/(app)/labels/page-e4fe11020bd7c7f3.js","/_next/static/chunks/app/(app)/layout-16ff7ec117adb330.js","/_next/static/chunks/app/(app)/logs/page-22ef90d51050ca6e.js","/_next/static/chunks/app/(app)/org/page-5798dadba188a30c.js","/_next/static/chunks/app/(app)/platform-activity/page-6a69a5a0ecefc377.js","/_next/static/chunks/app/(app)/platform-analytics/page-93e212b2deb26916.js","/_next/static/chunks/app/(app)/platform-companies/page-4fd3fcc06dc74d7e.js","/_next/static/chunks/app/(app)/platform-errors/page-e76ca1a151a95e71.js","/_next/static/chunks/app/(app)/platform-finance/page-b589e05d046a01d5.js","/_next/static/chunks/app/(app)/platform-leads/page-5b1d941522793d55.js","/_next/static/chunks/app/(app)/platform-plans/page-b76b9e727118ad77.js","/_next/static/chunks/app/(app)/platform-registrations/page-9ef7b6ad664302ae.js","/_next/static/chunks/app/(app)/platform-seo/page-d83ed560de7dfa4e.js","/_next/static/chunks/app/(app)/platform-subscriptions/page-6d1dc73145640a9e.js","/_next/static/chunks/app/(app)/platform-team/member/page-29e08cc89e29801a.js","/_next/static/chunks/app/(app)/platform-team/page-fb3c01874219f204.js","/_next/static/chunks/app/(app)/platform/page-b8cf1b50677acdc6.js","/_next/static/chunks/app/(app)/purchasing/page-d23568ea3079dd09.js","/_next/static/chunks/app/(app)/reports/page-8f9dcb61d8ca19a7.js","/_next/static/chunks/app/(app)/returns/page-a9a57b3ea21a5bb5.js","/_next/static/chunks/app/(app)/sales/page-53801f0a6511184e.js","/_next/static/chunks/app/(app)/settings/page-684ea05cb878cddd.js","/_next/static/chunks/app/(app)/subscription/page-c415606e8b0516c0.js","/_next/static/chunks/app/(app)/supplier-records/page-f3c9d9a3600e8c64.js","/_next/static/chunks/app/(app)/users/detail/page-9828d5cef1664dcd.js","/_next/static/chunks/app/(app)/users/page-87d16740363122ba.js","/_next/static/chunks/app/(app)/web-orders/page-089e4a38b98aaa2d.js","/_next/static/chunks/app/(app)/website/page-a6245635e4db3961.js","/_next/static/chunks/app/(marketing)/compare/[slug]/page-b40837170406f336.js","/_next/static/chunks/app/(marketing)/en/compare/[slug]/page-44c9204035a44cbb.js","/_next/static/chunks/app/(marketing)/en/guides/[slug]/page-9d0c612f643ebad2.js","/_next/static/chunks/app/(marketing)/en/guides/page-21f4550416c0fcb1.js","/_next/static/chunks/app/(marketing)/en/layout-bba71f66b30630d4.js","/_next/static/chunks/app/(marketing)/en/page-965a0ee6fe1c84e9.js","/_next/static/chunks/app/(marketing)/en/pricing/layout-bba71f66b30630d4.js","/_next/static/chunks/app/(marketing)/en/pricing/page-0670f7b899cadee4.js","/_next/static/chunks/app/(marketing)/en/product/layout-bba71f66b30630d4.js","/_next/static/chunks/app/(marketing)/en/product/page-3a228d69fc67a2d9.js","/_next/static/chunks/app/(marketing)/en/register/hosting/layout-bba71f66b30630d4.js","/_next/static/chunks/app/(marketing)/en/register/hosting/page-62a29d3bb86af1eb.js","/_next/static/chunks/app/(marketing)/en/register/layout-bba71f66b30630d4.js","/_next/static/chunks/app/(marketing)/en/register/page-b530434d56bb28e8.js","/_next/static/chunks/app/(marketing)/en/solutions/[slug]/page-8883f3312a1d0e33.js","/_next/static/chunks/app/(marketing)/en/solutions/page-ba8ed6f7c4756541.js","/_next/static/chunks/app/(marketing)/guides/[slug]/page-de65796fdbe64c8b.js","/_next/static/chunks/app/(marketing)/guides/page-de0afa96c6cd070b.js","/_next/static/chunks/app/(marketing)/layout-bba71f66b30630d4.js","/_next/static/chunks/app/(marketing)/page-810c53bfde0a6c96.js","/_next/static/chunks/app/(marketing)/pricing/layout-bba71f66b30630d4.js","/_next/static/chunks/app/(marketing)/pricing/page-7c9d0480d86f1249.js","/_next/static/chunks/app/(marketing)/product/layout-bba71f66b30630d4.js","/_next/static/chunks/app/(marketing)/product/page-d2028ef7c22da94d.js","/_next/static/chunks/app/(marketing)/register/hosting/layout-bba71f66b30630d4.js","/_next/static/chunks/app/(marketing)/register/hosting/page-28c1780dbf82c299.js","/_next/static/chunks/app/(marketing)/register/layout-bba71f66b30630d4.js","/_next/static/chunks/app/(marketing)/register/page-6f6917e9c7f1e5ce.js","/_next/static/chunks/app/(marketing)/solutions/[slug]/page-5b8cba022d9d0f39.js","/_next/static/chunks/app/(marketing)/solutions/page-8b41b5e80f651efe.js","/_next/static/chunks/app/_not-found/page-68a0584aa6a8d18f.js","/_next/static/chunks/app/activate-owner/layout-bba71f66b30630d4.js","/_next/static/chunks/app/activate-owner/page-71c2050e8cdc2235.js","/_next/static/chunks/app/forgot-password/layout-bba71f66b30630d4.js","/_next/static/chunks/app/forgot-password/page-afccc6b42c990caa.js","/_next/static/chunks/app/layout-1dc3f14ab2eee17c.js","/_next/static/chunks/app/login/layout-bba71f66b30630d4.js","/_next/static/chunks/app/login/page-ec57f65736c96325.js","/_next/static/chunks/app/reset-password/layout-bba71f66b30630d4.js","/_next/static/chunks/app/reset-password/page-070f2c7dbe84f6b0.js","/_next/static/chunks/app/robots.txt/route-bba71f66b30630d4.js","/_next/static/chunks/app/sitemap.xml/route-bba71f66b30630d4.js","/_next/static/chunks/e46ef968-b68f361a13319b06.js","/_next/static/chunks/framework-e856097ae3f00b5b.js","/_next/static/chunks/main-161e8115e5182cdb.js","/_next/static/chunks/main-app-3877a70d26e4c09e.js","/_next/static/chunks/pages/_app-d0a68f56507e1d03.js","/_next/static/chunks/pages/_error-87b7d7c4dcd46628.js","/_next/static/chunks/polyfills-42372ed130431b0a.js","/_next/static/chunks/webpack-2375102e4c95a2c5.js","/_next/static/css/0920dcf23d0d1726.css","/_next/static/media/011e180705008d6f-s.woff2","/_next/static/media/01f0c602c274ea55-s.woff2","/_next/static/media/19cfc7226ec3afaa-s.woff2","/_next/static/media/1ebb550cd0a67fc6-s.p.woff2","/_next/static/media/21350d82a1f187e9-s.woff2","/_next/static/media/350b852752f8489d-s.p.woff2","/_next/static/media/3dc379dc9b5dec12-s.p.woff2","/_next/static/media/58f386aa6b1a2a92-s.woff2","/_next/static/media/5ec84f17416dda4d-s.woff2","/_next/static/media/63a79a6cf340c5d2-s.p.woff2","/_next/static/media/7ba5fb2a8c88521c-s.woff2","/_next/static/media/8e9860b6e62d6359-s.woff2","/_next/static/media/92eeb95d069020cc-s.woff2","/_next/static/media/98e207f02528a563-s.p.woff2","/_next/static/media/99dcf268bda04fe5-s.woff2","/_next/static/media/ba9851c3c22cd980-s.woff2","/_next/static/media/c5f10e9e72d35c52-s.woff2","/_next/static/media/c5fe6dc8356a8c31-s.woff2","/_next/static/media/ce401babc0566bc1-s.woff2","/_next/static/media/d29838c109ef09b4-s.woff2","/_next/static/media/d3ebbfd689654d3a-s.p.woff2","/_next/static/media/dd994fbf464986f0-s.p.woff2","/_next/static/media/df0a9ae256c0569c-s.woff2","/_next/static/media/e40af3453d7c920a-s.woff2","/_next/static/media/e4af272ccee01ff0-s.p.woff2","/_next/static/media/e97026df054cf2a3-s.woff2","/_next/static/media/ef4d5661765d0e49-s.woff2","/_next/static/media/f15f45d13243c643-s.woff2","/icons/apple-touch-icon.png","/icons/icon-192.png","/icons/icon-512.png","/icons/icon-maskable-192.png","/icons/icon-maskable-512.png","/manifest.webmanifest"];
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
      cache.addAll([...new Set([...PRECACHE_PAGES, ...PRECACHE_APP_PAGES]), ...PRECACHE_ASSETS].map((url) => new Request(url, { cache: "reload" }))),
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

// Web Push from the server (core/push.py): a new order for this shop. The
// payload is small and self-contained; tapping opens the order.
self.addEventListener("push", (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch { data = { title: "Vezano", body: event.data?.text() || "" }; }
  event.waitUntil(
    self.registration.showNotification(data.title || "Vezano", {
      body: data.body || "",
      icon: "/icons/icon-192.png",
      badge: "/icons/icon-192.png",
      tag: data.tag || undefined,
      renotify: Boolean(data.tag),
      data: { url: data.url || "/web-orders/" },
      dir: "auto",
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL(event.notification.data?.url || "/web-orders/", self.location.origin).href;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
      const open = list.find((c) => "focus" in c);
      if (open) { open.navigate(url); return open.focus(); }
      return self.clients.openWindow(url);
    })
  );
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
    // The requested page only (with or without the trailing slash). Serving
    // another page's HTML — the old fallback handed out the POS — rendered
    // the wrong screen under the right address whenever a navigation was
    // slow or offline; the app hydrates the page in the HTML, not the URL.
    const url = new URL(request.url);
    const variants = [url.pathname, url.pathname.replace(/\/?$/, "/")];
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
