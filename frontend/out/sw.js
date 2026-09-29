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
const BUILD = "c542ByXJ_bpvk0wnBssig";
const CACHE = `vezano-shell-${BUILD}`;
// Every screen of the app, so the person lands on the page they asked for
// with no network — never on a different one. Filled in at build time from
// the export; the list below is the floor the PWA manifest relies on.
const PRECACHE_PAGES = ["/", "/login/", "/dashboard/", "/sales/", "/inventory/", "/returns/"];
const PRECACHE_APP_PAGES = ["/activate-owner/","/crm/","/customer-records/","/dashboard/","/debts/","/finance/","/forgot-password/","/hr/","/inventory/","/labels/","/login/","/logs/","/org/","/platform-activity/","/platform-analytics/","/platform-companies/","/platform-errors/","/platform-finance/","/platform-leads/","/platform-plans/","/platform-registrations/","/platform-seo/","/platform-subscriptions/","/platform-team/","/platform-team/member/","/platform/","/purchasing/","/reports/","/reset-password/","/returns/","/sales/","/settings/","/subscription/","/supplier-records/","/track/","/users/","/users/detail/","/web-orders/","/website/"];
// Every hashed chunk, stylesheet and font of this build, plus the manifest
// and icons — filled in at build time from the export.
const PRECACHE_ASSETS = ["/_next/static/c542ByXJ_bpvk0wnBssig/_buildManifest.js","/_next/static/c542ByXJ_bpvk0wnBssig/_ssgManifest.js","/_next/static/chunks/1328-f61aca8e87377237.js","/_next/static/chunks/1391-0b93ee9d9f7c21e5.js","/_next/static/chunks/1409-05db44ab90a94f3e.js","/_next/static/chunks/1698-66865647035d1996.js","/_next/static/chunks/2126-7b7217b357a0cfb8.js","/_next/static/chunks/2785-a68209e77807df85.js","/_next/static/chunks/2901-58c76605315b429d.js","/_next/static/chunks/3117-779e968607fe2cc6.js","/_next/static/chunks/3360-df2a082072b5c60d.js","/_next/static/chunks/3415-e416382187713410.js","/_next/static/chunks/3995-193cf33b08e91925.js","/_next/static/chunks/4023-df0da7eb8906d449.js","/_next/static/chunks/40b91c18-03576e02c01e0947.js","/_next/static/chunks/4200-086e4dd05ced843c.js","/_next/static/chunks/4265-6b8e540634aefe6a.js","/_next/static/chunks/4462.0f420d4f6374ab9b.js","/_next/static/chunks/4641-389f3f3aa4401584.js","/_next/static/chunks/476-91a03d2926c4bb1d.js","/_next/static/chunks/4838-398c296d08c00313.js","/_next/static/chunks/5405.a2853eec62072dae.js","/_next/static/chunks/5410-087bc64c21c04d17.js","/_next/static/chunks/55-4575a5b636cfe07c.js","/_next/static/chunks/5811-77cfd90ef1e6d3b9.js","/_next/static/chunks/6702-9ecb3cada27e6c6f.js","/_next/static/chunks/689-f7c6c557b5809682.js","/_next/static/chunks/694-73d22f93c292b472.js","/_next/static/chunks/7089-af84b523904bfac2.js","/_next/static/chunks/7536-15fbefc9cc695446.js","/_next/static/chunks/7769-313f6fad97c64c58.js","/_next/static/chunks/7941-031dfbdd1ceafa77.js","/_next/static/chunks/7985-d1895cf41b593f2a.js","/_next/static/chunks/8199-bd61374336f60601.js","/_next/static/chunks/8288-47bfec66ded80bcb.js","/_next/static/chunks/8430-f929184bb61c728a.js","/_next/static/chunks/8557.bdee3fe4b34fcf91.js","/_next/static/chunks/8890-e380b3deefae36d0.js","/_next/static/chunks/9242-8b7238ca5f101a62.js","/_next/static/chunks/9680-fbf07e2e2615a0c7.js","/_next/static/chunks/9681-f7fe59c4baa9d55d.js","/_next/static/chunks/9865-4a519997c0fdc178.js","/_next/static/chunks/app/(app)/crm/page-7a1811506ddce09f.js","/_next/static/chunks/app/(app)/customer-records/page-01c29c8aa160e965.js","/_next/static/chunks/app/(app)/dashboard/page-bc490bcb38a4814d.js","/_next/static/chunks/app/(app)/debts/page-1544ed6dce76e8df.js","/_next/static/chunks/app/(app)/finance/page-c1d8fb94f5889ace.js","/_next/static/chunks/app/(app)/hr/page-4b8be27379782ffa.js","/_next/static/chunks/app/(app)/inventory/page-6cc62b8ac284ad46.js","/_next/static/chunks/app/(app)/labels/page-b34b17f01b6b1031.js","/_next/static/chunks/app/(app)/layout-650e3e549265ee66.js","/_next/static/chunks/app/(app)/logs/page-8d2d60ab7e9ad3a9.js","/_next/static/chunks/app/(app)/org/page-8c78f01a38f89608.js","/_next/static/chunks/app/(app)/platform-activity/page-5ce483a836a34de8.js","/_next/static/chunks/app/(app)/platform-analytics/page-f80ec8a0622d20e5.js","/_next/static/chunks/app/(app)/platform-companies/page-8956e8dfb22bdb68.js","/_next/static/chunks/app/(app)/platform-errors/page-2e5010fd94cacb87.js","/_next/static/chunks/app/(app)/platform-finance/page-8132a28fb1868fbe.js","/_next/static/chunks/app/(app)/platform-leads/page-20207967f0a8ba0d.js","/_next/static/chunks/app/(app)/platform-plans/page-412355d0ee35856f.js","/_next/static/chunks/app/(app)/platform-registrations/page-55ec3fb45315550a.js","/_next/static/chunks/app/(app)/platform-seo/page-e5a822f5b3f48550.js","/_next/static/chunks/app/(app)/platform-subscriptions/page-2e25bad5061b775e.js","/_next/static/chunks/app/(app)/platform-team/member/page-728f5e5db7944965.js","/_next/static/chunks/app/(app)/platform-team/page-658e40881988ec63.js","/_next/static/chunks/app/(app)/platform/page-8d0974d193bc60ba.js","/_next/static/chunks/app/(app)/purchasing/page-2d55fa16366fe113.js","/_next/static/chunks/app/(app)/reports/page-1c4a85e23912aeb2.js","/_next/static/chunks/app/(app)/returns/page-b2a82f628370fd08.js","/_next/static/chunks/app/(app)/sales/page-c6c35fb1450f6431.js","/_next/static/chunks/app/(app)/settings/page-969f861f0d30d766.js","/_next/static/chunks/app/(app)/subscription/page-e0d9cceb6ab83fae.js","/_next/static/chunks/app/(app)/supplier-records/page-fc6eac6d71400ef5.js","/_next/static/chunks/app/(app)/users/detail/page-c92623b5fac19d6d.js","/_next/static/chunks/app/(app)/users/page-550ddba849b72e5a.js","/_next/static/chunks/app/(app)/web-orders/page-3932702d810ee37d.js","/_next/static/chunks/app/(app)/website/page-a68a89fe0ab06f7e.js","/_next/static/chunks/app/(marketing)/compare/[slug]/page-f3de3e70c8bf3448.js","/_next/static/chunks/app/(marketing)/en/compare/[slug]/page-d9eb8311bbab7e40.js","/_next/static/chunks/app/(marketing)/en/guides/[slug]/page-510022113e2546f2.js","/_next/static/chunks/app/(marketing)/en/guides/page-ff488629d8e278bb.js","/_next/static/chunks/app/(marketing)/en/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/en/page-3297a7810c9a5795.js","/_next/static/chunks/app/(marketing)/en/pricing/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/en/pricing/page-f338b10402dfbb12.js","/_next/static/chunks/app/(marketing)/en/product/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/en/product/page-ad778833e79f1ec4.js","/_next/static/chunks/app/(marketing)/en/register/hosting/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/en/register/hosting/page-e30785a730ae0e75.js","/_next/static/chunks/app/(marketing)/en/register/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/en/register/page-cf021a3877daeee2.js","/_next/static/chunks/app/(marketing)/en/solutions/[slug]/page-6833a6de229f2e29.js","/_next/static/chunks/app/(marketing)/en/solutions/page-fe1df55c9b7f93ec.js","/_next/static/chunks/app/(marketing)/en/track/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/en/track/page-a5dd3bf6b9a79ffb.js","/_next/static/chunks/app/(marketing)/guides/[slug]/page-fee889a0de5ee7ad.js","/_next/static/chunks/app/(marketing)/guides/page-e4a0517c8f340b0f.js","/_next/static/chunks/app/(marketing)/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/page-d6769e3cc6553212.js","/_next/static/chunks/app/(marketing)/pricing/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/pricing/page-3b4133348f88b30d.js","/_next/static/chunks/app/(marketing)/product/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/product/page-480a69b80f247d08.js","/_next/static/chunks/app/(marketing)/register/hosting/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/register/hosting/page-90ad55ae8afb51e1.js","/_next/static/chunks/app/(marketing)/register/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/register/page-476597497de00ba5.js","/_next/static/chunks/app/(marketing)/solutions/[slug]/page-482c9d947fd8617d.js","/_next/static/chunks/app/(marketing)/solutions/page-3d31c21aff09f122.js","/_next/static/chunks/app/(marketing)/track/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/track/page-05baf1655862bf86.js","/_next/static/chunks/app/_not-found/page-93f5ecd9b5a1b8d5.js","/_next/static/chunks/app/activate-owner/layout-9111370ccccd4922.js","/_next/static/chunks/app/activate-owner/page-b384164d0e13c0de.js","/_next/static/chunks/app/forgot-password/layout-9111370ccccd4922.js","/_next/static/chunks/app/forgot-password/page-e25a220a1db9cd98.js","/_next/static/chunks/app/layout-1da84fa04c98a656.js","/_next/static/chunks/app/login/layout-9111370ccccd4922.js","/_next/static/chunks/app/login/page-cb7ab5a646472f35.js","/_next/static/chunks/app/reset-password/layout-9111370ccccd4922.js","/_next/static/chunks/app/reset-password/page-263a638b50c49157.js","/_next/static/chunks/app/robots.txt/route-9111370ccccd4922.js","/_next/static/chunks/app/sitemap.xml/route-9111370ccccd4922.js","/_next/static/chunks/framework-ac871cde7d705c3a.js","/_next/static/chunks/main-61969269e7b3dad5.js","/_next/static/chunks/main-app-d3c2614b980cfab3.js","/_next/static/chunks/pages/_app-c0e3f7ff6ef43cb0.js","/_next/static/chunks/pages/_error-6bf3d2bf6fe2d033.js","/_next/static/chunks/polyfills-42372ed130431b0a.js","/_next/static/chunks/webpack-76fb0d753073358b.js","/_next/static/css/dd1f17b685719648.css","/_next/static/media/011e180705008d6f.woff2","/_next/static/media/19cfc7226ec3afaa.woff2","/_next/static/media/1ebb550cd0a67fc6.p.woff2","/_next/static/media/21350d82a1f187e9.woff2","/_next/static/media/3dc379dc9b5dec12.p.woff2","/_next/static/media/58c726479f69cacd.woff2","/_next/static/media/58f386aa6b1a2a92.woff2","/_next/static/media/63a79a6cf340c5d2.p.woff2","/_next/static/media/7ba5fb2a8c88521c.woff2","/_next/static/media/8e9860b6e62d6359.woff2","/_next/static/media/92eeb95d069020cc.woff2","/_next/static/media/98e207f02528a563.p.woff2","/_next/static/media/99dcf268bda04fe5.woff2","/_next/static/media/ba9851c3c22cd980.woff2","/_next/static/media/bd9c8c62ffadd9dd.p.woff2","/_next/static/media/c5f10e9e72d35c52.woff2","/_next/static/media/c5fe6dc8356a8c31.woff2","/_next/static/media/cc8b755e9c1ba115.woff2","/_next/static/media/ce401babc0566bc1.woff2","/_next/static/media/d29838c109ef09b4.woff2","/_next/static/media/d3ebbfd689654d3a.p.woff2","/_next/static/media/dd994fbf464986f0.p.woff2","/_next/static/media/df0a9ae256c0569c.woff2","/_next/static/media/e40af3453d7c920a.woff2","/_next/static/media/e4af272ccee01ff0.p.woff2","/_next/static/media/e97026df054cf2a3.woff2","/_next/static/media/ef4d5661765d0e49.woff2","/_next/static/media/f15f45d13243c643.woff2","/_next/static/media/f952393b67d608ec.p.woff2","/icons/apple-touch-icon.png","/icons/badge-96.png","/icons/icon-192.png","/icons/icon-512.png","/icons/icon-maskable-192.png","/icons/icon-maskable-512.png","/manifest.webmanifest"];
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
  try { data = event.data ? event.data.json() : {}; } catch { data = { title: "Vezano Pro", body: event.data?.text() || "" }; }
  event.waitUntil(
    self.registration.showNotification(data.title || "Vezano Pro", {
      body: data.body || "",
      icon: "/icons/icon-192.png",
      badge: "/icons/badge-96.png",
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
      "<!doctype html><meta charset=utf-8><title>Vezano Pro</title>" +
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
