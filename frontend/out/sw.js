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
const BUILD = "Z5rLnmrFq2VEsKiCi490F";
const CACHE = `vezano-shell-${BUILD}`;
// Every screen of the app, so the person lands on the page they asked for
// with no network — never on a different one. Filled in at build time from
// the export; the list below is the floor the PWA manifest relies on.
const PRECACHE_PAGES = ["/", "/login/", "/dashboard/", "/sales/", "/inventory/", "/returns/"];
const PRECACHE_APP_PAGES = ["/activate-owner/","/crm/","/customer-records/","/dashboard/","/debts/","/finance/","/forgot-password/","/hr/","/inventory/","/labels/","/login/","/logs/","/org/","/platform-activity/","/platform-analytics/","/platform-companies/","/platform-errors/","/platform-finance/","/platform-leads/","/platform-plans/","/platform-registrations/","/platform-seo/","/platform-subscriptions/","/platform-team/","/platform-team/member/","/platform/","/purchasing/","/reports/","/reset-password/","/returns/","/sales/","/settings/","/subscription/","/supplier-records/","/track/","/users/","/users/detail/","/web-orders/","/website/"];
// Every hashed chunk, stylesheet and font of this build, plus the manifest
// and icons — filled in at build time from the export.
const PRECACHE_ASSETS = ["/_next/static/Z5rLnmrFq2VEsKiCi490F/_buildManifest.js","/_next/static/Z5rLnmrFq2VEsKiCi490F/_ssgManifest.js","/_next/static/chunks/1391-0b93ee9d9f7c21e5.js","/_next/static/chunks/182-f26e88b724bd5e6e.js","/_next/static/chunks/2043-ab8d65b29ba0473b.js","/_next/static/chunks/2126-24867736d9f03e4f.js","/_next/static/chunks/2785-31913625a873f56c.js","/_next/static/chunks/2900-6389ebc776f71036.js","/_next/static/chunks/3095-0d2ddb919bf24733.js","/_next/static/chunks/3117-61a68afb919b8d59.js","/_next/static/chunks/3233-e5ee82c754225131.js","/_next/static/chunks/3415-ccbb2a678c4feba6.js","/_next/static/chunks/3995-193cf33b08e91925.js","/_next/static/chunks/40b91c18-03576e02c01e0947.js","/_next/static/chunks/4265-b66f7ac538ee3086.js","/_next/static/chunks/4462.0f420d4f6374ab9b.js","/_next/static/chunks/476-7813f4e63e52b863.js","/_next/static/chunks/4838-bb67455c9d25c74f.js","/_next/static/chunks/4840-b77d89b8f443e562.js","/_next/static/chunks/5405.a2853eec62072dae.js","/_next/static/chunks/5410-087bc64c21c04d17.js","/_next/static/chunks/5811-c5306e37bd205f86.js","/_next/static/chunks/6578-7749d7797e4a7b3d.js","/_next/static/chunks/689-a0465b186118c2fe.js","/_next/static/chunks/694-73d22f93c292b472.js","/_next/static/chunks/7089-af84b523904bfac2.js","/_next/static/chunks/7171-9011a40e11bc5d3d.js","/_next/static/chunks/7535-97fb2c0a316b2407.js","/_next/static/chunks/7536-15fbefc9cc695446.js","/_next/static/chunks/7769-313f6fad97c64c58.js","/_next/static/chunks/7787-ec2935a2617cacbc.js","/_next/static/chunks/7838-a2540f8ab8a2327e.js","/_next/static/chunks/7941-858e5f9da605dd72.js","/_next/static/chunks/8199-b7822f9e69122fc5.js","/_next/static/chunks/8349-b82cd7992f651feb.js","/_next/static/chunks/8430-f929184bb61c728a.js","/_next/static/chunks/8557.bdee3fe4b34fcf91.js","/_next/static/chunks/869-69ca79896c11c825.js","/_next/static/chunks/8690-c26d04baf9f5d41e.js","/_next/static/chunks/8890-93390470aa87db92.js","/_next/static/chunks/9042-b49e79ea83899799.js","/_next/static/chunks/9242-5dadef187f312ae1.js","/_next/static/chunks/9535-13712210b96ba167.js","/_next/static/chunks/9865-993a8f72dbe829c9.js","/_next/static/chunks/9960-228345031546f838.js","/_next/static/chunks/app/(app)/crm/page-74a00e50f607a0b2.js","/_next/static/chunks/app/(app)/customer-records/page-ddcc6d56fe8b40bc.js","/_next/static/chunks/app/(app)/dashboard/page-d449b337eb0ece56.js","/_next/static/chunks/app/(app)/debts/page-6e0859c92dbed760.js","/_next/static/chunks/app/(app)/finance/page-6ac347c0e61310e9.js","/_next/static/chunks/app/(app)/hr/page-f97fcf3806d183ea.js","/_next/static/chunks/app/(app)/inventory/page-19f4a73a49812bf4.js","/_next/static/chunks/app/(app)/labels/page-8a5f352ac084aa47.js","/_next/static/chunks/app/(app)/layout-8892454393f757e9.js","/_next/static/chunks/app/(app)/logs/page-0840e6fd93012f84.js","/_next/static/chunks/app/(app)/org/page-8981fa7afead4608.js","/_next/static/chunks/app/(app)/platform-activity/page-e4b1b851703de5f1.js","/_next/static/chunks/app/(app)/platform-analytics/page-6e67ff58f0985c8f.js","/_next/static/chunks/app/(app)/platform-companies/page-7c761abc335ab9c4.js","/_next/static/chunks/app/(app)/platform-errors/page-53076c4f2d598a04.js","/_next/static/chunks/app/(app)/platform-finance/page-713877ff33754f93.js","/_next/static/chunks/app/(app)/platform-leads/page-03db216f38860a6f.js","/_next/static/chunks/app/(app)/platform-plans/page-7c6252db7db9c38e.js","/_next/static/chunks/app/(app)/platform-registrations/page-1a5c18304042aca1.js","/_next/static/chunks/app/(app)/platform-seo/page-8c78c411d6b969a0.js","/_next/static/chunks/app/(app)/platform-subscriptions/page-d5d9a799e6e8896a.js","/_next/static/chunks/app/(app)/platform-team/member/page-dcedf182061e6432.js","/_next/static/chunks/app/(app)/platform-team/page-bfde1f58caab191c.js","/_next/static/chunks/app/(app)/platform/page-d54a6435ca8ee277.js","/_next/static/chunks/app/(app)/purchasing/page-279400ba99634f61.js","/_next/static/chunks/app/(app)/reports/page-811ae93692ad9310.js","/_next/static/chunks/app/(app)/returns/page-3049cb47148b67ea.js","/_next/static/chunks/app/(app)/sales/page-992a282857e4e130.js","/_next/static/chunks/app/(app)/settings/page-cf4b67dbe14e9a09.js","/_next/static/chunks/app/(app)/subscription/page-7e975279dced8a84.js","/_next/static/chunks/app/(app)/supplier-records/page-5ab793318367494f.js","/_next/static/chunks/app/(app)/users/detail/page-c24d5b55d78c60ce.js","/_next/static/chunks/app/(app)/users/page-39308edd99ad2d73.js","/_next/static/chunks/app/(app)/web-orders/page-b904ddcf4e12f9e7.js","/_next/static/chunks/app/(app)/website/page-c4648107ebac5201.js","/_next/static/chunks/app/(marketing)/compare/[slug]/page-1810d368d5b2c230.js","/_next/static/chunks/app/(marketing)/en/compare/[slug]/page-b85362e65d2e6b10.js","/_next/static/chunks/app/(marketing)/en/guides/[slug]/page-7f8804c6aa0101d2.js","/_next/static/chunks/app/(marketing)/en/guides/page-f2d648956468b9ad.js","/_next/static/chunks/app/(marketing)/en/layout-ddaba7143b3b003d.js","/_next/static/chunks/app/(marketing)/en/page-3e31d785565e7896.js","/_next/static/chunks/app/(marketing)/en/pricing/layout-ddaba7143b3b003d.js","/_next/static/chunks/app/(marketing)/en/pricing/page-0c2460cdde19d12a.js","/_next/static/chunks/app/(marketing)/en/product/layout-ddaba7143b3b003d.js","/_next/static/chunks/app/(marketing)/en/product/page-609072dcb1458810.js","/_next/static/chunks/app/(marketing)/en/register/hosting/layout-ddaba7143b3b003d.js","/_next/static/chunks/app/(marketing)/en/register/hosting/page-77321e621f283da7.js","/_next/static/chunks/app/(marketing)/en/register/layout-ddaba7143b3b003d.js","/_next/static/chunks/app/(marketing)/en/register/page-473fddec2756054b.js","/_next/static/chunks/app/(marketing)/en/solutions/[slug]/page-aff2049a468c37fb.js","/_next/static/chunks/app/(marketing)/en/solutions/page-468ea6838e6284d0.js","/_next/static/chunks/app/(marketing)/en/track/layout-ddaba7143b3b003d.js","/_next/static/chunks/app/(marketing)/en/track/page-d35635cd0d6c77c7.js","/_next/static/chunks/app/(marketing)/guides/[slug]/page-d8b9e8821fe8ea5c.js","/_next/static/chunks/app/(marketing)/guides/page-faf404ca066d07c1.js","/_next/static/chunks/app/(marketing)/layout-dc19b7d291f16f7e.js","/_next/static/chunks/app/(marketing)/page-6eaa9a5ef66ccbb7.js","/_next/static/chunks/app/(marketing)/pricing/layout-ddaba7143b3b003d.js","/_next/static/chunks/app/(marketing)/pricing/page-36b128434582dfa3.js","/_next/static/chunks/app/(marketing)/product/layout-ddaba7143b3b003d.js","/_next/static/chunks/app/(marketing)/product/page-95214bcbfe3fe7cd.js","/_next/static/chunks/app/(marketing)/register/hosting/layout-ddaba7143b3b003d.js","/_next/static/chunks/app/(marketing)/register/hosting/page-c9a50a71f306ff9c.js","/_next/static/chunks/app/(marketing)/register/layout-ddaba7143b3b003d.js","/_next/static/chunks/app/(marketing)/register/page-330314747cae70bd.js","/_next/static/chunks/app/(marketing)/solutions/[slug]/page-fb6b757ef9c98fb9.js","/_next/static/chunks/app/(marketing)/solutions/page-b1b89c3cd7bbfb6c.js","/_next/static/chunks/app/(marketing)/track/layout-ddaba7143b3b003d.js","/_next/static/chunks/app/(marketing)/track/page-de05de578bf276d5.js","/_next/static/chunks/app/_not-found/page-93f5ecd9b5a1b8d5.js","/_next/static/chunks/app/activate-owner/layout-897207abf8b741a6.js","/_next/static/chunks/app/activate-owner/page-db613b20b072142a.js","/_next/static/chunks/app/forgot-password/layout-897207abf8b741a6.js","/_next/static/chunks/app/forgot-password/page-582e37086645d5fa.js","/_next/static/chunks/app/layout-bcdc8d551d078b4f.js","/_next/static/chunks/app/login/layout-897207abf8b741a6.js","/_next/static/chunks/app/login/page-ad2a615c293dd0cf.js","/_next/static/chunks/app/reset-password/layout-897207abf8b741a6.js","/_next/static/chunks/app/reset-password/page-5324540b32a8c8ef.js","/_next/static/chunks/app/robots.txt/route-ddaba7143b3b003d.js","/_next/static/chunks/app/sitemap.xml/route-ddaba7143b3b003d.js","/_next/static/chunks/framework-ac871cde7d705c3a.js","/_next/static/chunks/main-61969269e7b3dad5.js","/_next/static/chunks/main-app-d3c2614b980cfab3.js","/_next/static/chunks/pages/_app-c0e3f7ff6ef43cb0.js","/_next/static/chunks/pages/_error-6bf3d2bf6fe2d033.js","/_next/static/chunks/polyfills-42372ed130431b0a.js","/_next/static/chunks/webpack-e2d07945ef8a22a4.js","/_next/static/css/3f59adeb3c222c1c.css","/_next/static/css/4fc28e63c85ceac5.css","/_next/static/media/011e180705008d6f.woff2","/_next/static/media/19cfc7226ec3afaa.woff2","/_next/static/media/1ebb550cd0a67fc6.p.woff2","/_next/static/media/21350d82a1f187e9.woff2","/_next/static/media/3dc379dc9b5dec12.p.woff2","/_next/static/media/58c726479f69cacd.woff2","/_next/static/media/58f386aa6b1a2a92.woff2","/_next/static/media/63a79a6cf340c5d2.p.woff2","/_next/static/media/7ba5fb2a8c88521c.woff2","/_next/static/media/8e9860b6e62d6359.woff2","/_next/static/media/92eeb95d069020cc.woff2","/_next/static/media/98e207f02528a563.p.woff2","/_next/static/media/99dcf268bda04fe5.woff2","/_next/static/media/ba9851c3c22cd980.woff2","/_next/static/media/bd9c8c62ffadd9dd.p.woff2","/_next/static/media/c5f10e9e72d35c52.woff2","/_next/static/media/c5fe6dc8356a8c31.woff2","/_next/static/media/cc8b755e9c1ba115.woff2","/_next/static/media/ce401babc0566bc1.woff2","/_next/static/media/d29838c109ef09b4.woff2","/_next/static/media/d3ebbfd689654d3a.p.woff2","/_next/static/media/dd994fbf464986f0.p.woff2","/_next/static/media/df0a9ae256c0569c.woff2","/_next/static/media/e40af3453d7c920a.woff2","/_next/static/media/e4af272ccee01ff0.p.woff2","/_next/static/media/e97026df054cf2a3.woff2","/_next/static/media/ef4d5661765d0e49.woff2","/_next/static/media/f15f45d13243c643.woff2","/_next/static/media/f952393b67d608ec.p.woff2","/icons/apple-touch-icon.png","/icons/badge-96.png","/icons/icon-192.png","/icons/icon-512.png","/icons/icon-maskable-192.png","/icons/icon-maskable-512.png","/manifest.webmanifest"];
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
