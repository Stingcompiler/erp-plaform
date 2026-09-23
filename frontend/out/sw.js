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
const BUILD = "UX9hk8JEMRPiVQETe4m-X";
const CACHE = `vezano-shell-${BUILD}`;
// Every screen of the app, so the person lands on the page they asked for
// with no network — never on a different one. Filled in at build time from
// the export; the list below is the floor the PWA manifest relies on.
const PRECACHE_PAGES = ["/", "/login/", "/dashboard/", "/sales/", "/inventory/", "/returns/"];
const PRECACHE_APP_PAGES = ["/activate-owner/","/crm/","/customer-records/","/dashboard/","/debts/","/finance/","/forgot-password/","/hr/","/inventory/","/labels/","/login/","/logs/","/org/","/platform-activity/","/platform-analytics/","/platform-companies/","/platform-errors/","/platform-finance/","/platform-leads/","/platform-plans/","/platform-registrations/","/platform-seo/","/platform-subscriptions/","/platform-team/","/platform-team/member/","/platform/","/purchasing/","/reports/","/reset-password/","/returns/","/sales/","/settings/","/subscription/","/supplier-records/","/users/","/users/detail/","/web-orders/","/website/"];
// Every hashed chunk, stylesheet and font of this build, plus the manifest
// and icons — filled in at build time from the export.
const PRECACHE_ASSETS = ["/_next/static/UX9hk8JEMRPiVQETe4m-X/_buildManifest.js","/_next/static/UX9hk8JEMRPiVQETe4m-X/_ssgManifest.js","/_next/static/chunks/1228-5dff63c581a7eb54.js","/_next/static/chunks/1255-f456c2191ed027a9.js","/_next/static/chunks/1360-1e072e785e353f8e.js","/_next/static/chunks/1597-571d6d678f664d18.js","/_next/static/chunks/1947-7f694d73ceb83d2f.js","/_next/static/chunks/1966-7433a01b946bfb65.js","/_next/static/chunks/2101-5378103311b9bf0b.js","/_next/static/chunks/2145-cdd2da8f8a3158af.js","/_next/static/chunks/2320-891c6128e0368396.js","/_next/static/chunks/280-43d2951a75ccb567.js","/_next/static/chunks/3302-d029ab2f9bb59496.js","/_next/static/chunks/3607-791e993e0570ac1b.js","/_next/static/chunks/4050-bf10c63038e403ad.js","/_next/static/chunks/4059-537091c40bc36e38.js","/_next/static/chunks/4066-9c44c76ca71c7923.js","/_next/static/chunks/4121-487ca342d6599963.js","/_next/static/chunks/4338-713a906bf9efab5b.js","/_next/static/chunks/4796-ddc6021c16d1db57.js","/_next/static/chunks/4bd1b696-100b9d70ed4e49c1.js","/_next/static/chunks/5053-daa9a1d8bc24425a.js","/_next/static/chunks/5421.5361245639e5cbb3.js","/_next/static/chunks/5917-88776841fc058658.js","/_next/static/chunks/725-7424a382a355fca9.js","/_next/static/chunks/7289-ce2dea732489a2b2.js","/_next/static/chunks/7423-05ed8008b69fb116.js","/_next/static/chunks/7865-52eda843c908da3b.js","/_next/static/chunks/8679-d4b12ab3c4030c30.js","/_next/static/chunks/8838-0764cda4a58c0fa6.js","/_next/static/chunks/8944-d9d3a940691b238e.js","/_next/static/chunks/9475-6050b30be54033fb.js","/_next/static/chunks/app/(app)/crm/page-c019b8c7ba00e4a5.js","/_next/static/chunks/app/(app)/customer-records/page-547731f1b39f59a9.js","/_next/static/chunks/app/(app)/dashboard/page-bd2264d10d40dafc.js","/_next/static/chunks/app/(app)/debts/page-249630af49882baf.js","/_next/static/chunks/app/(app)/finance/page-cb7f6d876fcf3b82.js","/_next/static/chunks/app/(app)/hr/page-290dde14d31b913b.js","/_next/static/chunks/app/(app)/inventory/page-eec3014f6ed7ac0f.js","/_next/static/chunks/app/(app)/labels/page-64442b578cf9e560.js","/_next/static/chunks/app/(app)/layout-aecbb441ad76a850.js","/_next/static/chunks/app/(app)/logs/page-5318d1b43d650e3d.js","/_next/static/chunks/app/(app)/org/page-64b3909c56795271.js","/_next/static/chunks/app/(app)/platform-activity/page-01cbd63125852299.js","/_next/static/chunks/app/(app)/platform-analytics/page-5f516a366699b7d5.js","/_next/static/chunks/app/(app)/platform-companies/page-fa835b64a7b7fc77.js","/_next/static/chunks/app/(app)/platform-errors/page-c56b594505a0565f.js","/_next/static/chunks/app/(app)/platform-finance/page-921550bbbd20ec69.js","/_next/static/chunks/app/(app)/platform-leads/page-3250428fea80661e.js","/_next/static/chunks/app/(app)/platform-plans/page-5f0749ab116e8df4.js","/_next/static/chunks/app/(app)/platform-registrations/page-8c1990f47cb658c0.js","/_next/static/chunks/app/(app)/platform-seo/page-ca0928c80192d006.js","/_next/static/chunks/app/(app)/platform-subscriptions/page-88a4f9ee28825570.js","/_next/static/chunks/app/(app)/platform-team/member/page-e11dd3a79ee0e1f5.js","/_next/static/chunks/app/(app)/platform-team/page-3454a6373a187cb1.js","/_next/static/chunks/app/(app)/platform/page-bec158170dbd8f6d.js","/_next/static/chunks/app/(app)/purchasing/page-756d094cda05d222.js","/_next/static/chunks/app/(app)/reports/page-faf22e14e96c1296.js","/_next/static/chunks/app/(app)/returns/page-80543244b047e62e.js","/_next/static/chunks/app/(app)/sales/page-297e168a6fbecc86.js","/_next/static/chunks/app/(app)/settings/page-3d882b911f21d9e0.js","/_next/static/chunks/app/(app)/subscription/page-81a355bbcde95ce9.js","/_next/static/chunks/app/(app)/supplier-records/page-5f07046bd1b98dd9.js","/_next/static/chunks/app/(app)/users/detail/page-2b57161ae9ccdeba.js","/_next/static/chunks/app/(app)/users/page-d6cef0e06cd57db8.js","/_next/static/chunks/app/(app)/web-orders/page-bfa40965e814d458.js","/_next/static/chunks/app/(app)/website/page-337277429fb5b85d.js","/_next/static/chunks/app/(marketing)/compare/[slug]/page-33638d2c8e60f19a.js","/_next/static/chunks/app/(marketing)/en/compare/[slug]/page-9a0e56b3fc8b3a29.js","/_next/static/chunks/app/(marketing)/en/guides/[slug]/page-fc2d093b174acaa4.js","/_next/static/chunks/app/(marketing)/en/guides/page-e2c8d5dce553909e.js","/_next/static/chunks/app/(marketing)/en/layout-932326ab10ba2957.js","/_next/static/chunks/app/(marketing)/en/page-93807a000ab77b10.js","/_next/static/chunks/app/(marketing)/en/pricing/layout-932326ab10ba2957.js","/_next/static/chunks/app/(marketing)/en/pricing/page-a625a78659054e9b.js","/_next/static/chunks/app/(marketing)/en/product/layout-932326ab10ba2957.js","/_next/static/chunks/app/(marketing)/en/product/page-77e08a6b6906dc92.js","/_next/static/chunks/app/(marketing)/en/register/hosting/layout-932326ab10ba2957.js","/_next/static/chunks/app/(marketing)/en/register/hosting/page-3175e0ab70091ee0.js","/_next/static/chunks/app/(marketing)/en/register/layout-932326ab10ba2957.js","/_next/static/chunks/app/(marketing)/en/register/page-f51bf2e41a822561.js","/_next/static/chunks/app/(marketing)/en/solutions/[slug]/page-17bfa5d0693f32a8.js","/_next/static/chunks/app/(marketing)/en/solutions/page-3a50f0f0e6daa87d.js","/_next/static/chunks/app/(marketing)/guides/[slug]/page-316571e1a6a1fe90.js","/_next/static/chunks/app/(marketing)/guides/page-a1a668c794a7ef5d.js","/_next/static/chunks/app/(marketing)/layout-932326ab10ba2957.js","/_next/static/chunks/app/(marketing)/page-ad520c0cbaefcb86.js","/_next/static/chunks/app/(marketing)/pricing/layout-932326ab10ba2957.js","/_next/static/chunks/app/(marketing)/pricing/page-540fb435401c64d5.js","/_next/static/chunks/app/(marketing)/product/layout-932326ab10ba2957.js","/_next/static/chunks/app/(marketing)/product/page-f5979aedebfb6725.js","/_next/static/chunks/app/(marketing)/register/hosting/layout-932326ab10ba2957.js","/_next/static/chunks/app/(marketing)/register/hosting/page-879da04235ffaa5f.js","/_next/static/chunks/app/(marketing)/register/layout-932326ab10ba2957.js","/_next/static/chunks/app/(marketing)/register/page-957646ad27c008a2.js","/_next/static/chunks/app/(marketing)/solutions/[slug]/page-12851bd995de1acf.js","/_next/static/chunks/app/(marketing)/solutions/page-a6d521013bd7d29a.js","/_next/static/chunks/app/_not-found/page-fb60ccb3ed4b5a30.js","/_next/static/chunks/app/activate-owner/layout-932326ab10ba2957.js","/_next/static/chunks/app/activate-owner/page-f53158ad074f42ab.js","/_next/static/chunks/app/forgot-password/layout-932326ab10ba2957.js","/_next/static/chunks/app/forgot-password/page-41b065ad45e49543.js","/_next/static/chunks/app/layout-b9ccc2c3febdba8a.js","/_next/static/chunks/app/login/layout-932326ab10ba2957.js","/_next/static/chunks/app/login/page-7354c2a09e7cab06.js","/_next/static/chunks/app/reset-password/layout-932326ab10ba2957.js","/_next/static/chunks/app/reset-password/page-82cab0bf7203eae8.js","/_next/static/chunks/app/robots.txt/route-932326ab10ba2957.js","/_next/static/chunks/app/sitemap.xml/route-932326ab10ba2957.js","/_next/static/chunks/framework-4374eae96780d8a1.js","/_next/static/chunks/main-app-282bc9487decc98d.js","/_next/static/chunks/main-bad072af1eaab979.js","/_next/static/chunks/pages/_app-4b3fb5e477a0267f.js","/_next/static/chunks/pages/_error-c970d8b55ace1b48.js","/_next/static/chunks/polyfills-42372ed130431b0a.js","/_next/static/chunks/webpack-9c2ac852f8579a6b.js","/_next/static/css/d160f8efca8307a9.css","/_next/static/media/011e180705008d6f-s.woff2","/_next/static/media/01f0c602c274ea55-s.woff2","/_next/static/media/19cfc7226ec3afaa-s.woff2","/_next/static/media/1ebb550cd0a67fc6-s.p.woff2","/_next/static/media/21350d82a1f187e9-s.woff2","/_next/static/media/350b852752f8489d-s.p.woff2","/_next/static/media/3dc379dc9b5dec12-s.p.woff2","/_next/static/media/58f386aa6b1a2a92-s.woff2","/_next/static/media/5ec84f17416dda4d-s.woff2","/_next/static/media/63a79a6cf340c5d2-s.p.woff2","/_next/static/media/7ba5fb2a8c88521c-s.woff2","/_next/static/media/8e9860b6e62d6359-s.woff2","/_next/static/media/92eeb95d069020cc-s.woff2","/_next/static/media/98e207f02528a563-s.p.woff2","/_next/static/media/99dcf268bda04fe5-s.woff2","/_next/static/media/ba9851c3c22cd980-s.woff2","/_next/static/media/c5f10e9e72d35c52-s.woff2","/_next/static/media/c5fe6dc8356a8c31-s.woff2","/_next/static/media/ce401babc0566bc1-s.woff2","/_next/static/media/d29838c109ef09b4-s.woff2","/_next/static/media/d3ebbfd689654d3a-s.p.woff2","/_next/static/media/dd994fbf464986f0-s.p.woff2","/_next/static/media/df0a9ae256c0569c-s.woff2","/_next/static/media/e40af3453d7c920a-s.woff2","/_next/static/media/e4af272ccee01ff0-s.p.woff2","/_next/static/media/e97026df054cf2a3-s.woff2","/_next/static/media/ef4d5661765d0e49-s.woff2","/_next/static/media/f15f45d13243c643-s.woff2","/icons/apple-touch-icon.png","/icons/icon-192.png","/icons/icon-512.png","/icons/icon-maskable-192.png","/icons/icon-maskable-512.png","/manifest.webmanifest"];
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
