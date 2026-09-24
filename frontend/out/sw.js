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
const BUILD = "M8BUi_V1AjWJhtqFkJOw2";
const CACHE = `vezano-shell-${BUILD}`;
// Every screen of the app, so the person lands on the page they asked for
// with no network — never on a different one. Filled in at build time from
// the export; the list below is the floor the PWA manifest relies on.
const PRECACHE_PAGES = ["/", "/login/", "/dashboard/", "/sales/", "/inventory/", "/returns/"];
const PRECACHE_APP_PAGES = ["/activate-owner/","/crm/","/customer-records/","/dashboard/","/debts/","/finance/","/forgot-password/","/hr/","/inventory/","/labels/","/login/","/logs/","/org/","/platform-activity/","/platform-analytics/","/platform-companies/","/platform-errors/","/platform-finance/","/platform-leads/","/platform-plans/","/platform-registrations/","/platform-seo/","/platform-subscriptions/","/platform-team/","/platform-team/member/","/platform/","/purchasing/","/reports/","/reset-password/","/returns/","/sales/","/settings/","/subscription/","/supplier-records/","/users/","/users/detail/","/web-orders/","/website/"];
// Every hashed chunk, stylesheet and font of this build, plus the manifest
// and icons — filled in at build time from the export.
const PRECACHE_ASSETS = ["/_next/static/M8BUi_V1AjWJhtqFkJOw2/_buildManifest.js","/_next/static/M8BUi_V1AjWJhtqFkJOw2/_ssgManifest.js","/_next/static/chunks/1391-d5c258545ac8820c.js","/_next/static/chunks/2126-d8ba67c1bb54e773.js","/_next/static/chunks/2395-2840df6565c7c063.js","/_next/static/chunks/2901-401f1a92695f4c98.js","/_next/static/chunks/3415-f9bd92857bb9735e.js","/_next/static/chunks/3719-8637407c9cdd483d.js","/_next/static/chunks/3995-193cf33b08e91925.js","/_next/static/chunks/40b91c18-03576e02c01e0947.js","/_next/static/chunks/4200-086e4dd05ced843c.js","/_next/static/chunks/4473-acbbb3b1e30980db.js","/_next/static/chunks/4838-379e2894ffa4b949.js","/_next/static/chunks/5127-8ce8e51bca0fc7a3.js","/_next/static/chunks/5270-fd78028256dbaba0.js","/_next/static/chunks/5405.a2853eec62072dae.js","/_next/static/chunks/5410-087bc64c21c04d17.js","/_next/static/chunks/5950-b6379abbc401e4c6.js","/_next/static/chunks/6055-fd695756aec085b1.js","/_next/static/chunks/6195-a72507a58c25e6da.js","/_next/static/chunks/6472-6ce7a3cce4a6401b.js","/_next/static/chunks/6702-5a33da0ccd8afcac.js","/_next/static/chunks/6762-5721c03a60cb2fdc.js","/_next/static/chunks/7670-8a6cbb8afe75648b.js","/_next/static/chunks/7733-a48a609e5b8d8a1f.js","/_next/static/chunks/7769-313f6fad97c64c58.js","/_next/static/chunks/8117-7b8cad2342bec1fa.js","/_next/static/chunks/8430-f929184bb61c728a.js","/_next/static/chunks/9168-d05e34c5227b0c56.js","/_next/static/chunks/9265-6ce767b10af0b932.js","/_next/static/chunks/9615-f70fb75953e94f64.js","/_next/static/chunks/9695-980d890a9c9ebf92.js","/_next/static/chunks/app/(app)/crm/page-fb1822bea855a200.js","/_next/static/chunks/app/(app)/customer-records/page-1d905e4a0e04fb58.js","/_next/static/chunks/app/(app)/dashboard/page-073a099fb07fd8d0.js","/_next/static/chunks/app/(app)/debts/page-31c2bb2315e596b5.js","/_next/static/chunks/app/(app)/finance/page-25edb98811f330a2.js","/_next/static/chunks/app/(app)/hr/page-06a59c66c3353974.js","/_next/static/chunks/app/(app)/inventory/page-a942f0e5a011c7e9.js","/_next/static/chunks/app/(app)/labels/page-ba5a4148e6d84024.js","/_next/static/chunks/app/(app)/layout-5f3bfa76091dc3cc.js","/_next/static/chunks/app/(app)/logs/page-907c2462e378d901.js","/_next/static/chunks/app/(app)/org/page-369151eba2cf4e4d.js","/_next/static/chunks/app/(app)/platform-activity/page-11ff824616fcd845.js","/_next/static/chunks/app/(app)/platform-analytics/page-dc8b9bd69adace72.js","/_next/static/chunks/app/(app)/platform-companies/page-89c53cff053d0463.js","/_next/static/chunks/app/(app)/platform-errors/page-087b09652083a6bd.js","/_next/static/chunks/app/(app)/platform-finance/page-a772c06117a93ce1.js","/_next/static/chunks/app/(app)/platform-leads/page-5333bcf80be0055f.js","/_next/static/chunks/app/(app)/platform-plans/page-5837feb99b9e8f23.js","/_next/static/chunks/app/(app)/platform-registrations/page-08c379b47e2cbe3a.js","/_next/static/chunks/app/(app)/platform-seo/page-a58320f03ef523ca.js","/_next/static/chunks/app/(app)/platform-subscriptions/page-548901996b1493f7.js","/_next/static/chunks/app/(app)/platform-team/member/page-cae39b836396c88a.js","/_next/static/chunks/app/(app)/platform-team/page-abecd5d8408e8507.js","/_next/static/chunks/app/(app)/platform/page-752977d20069faa4.js","/_next/static/chunks/app/(app)/purchasing/page-88d7ae016759a950.js","/_next/static/chunks/app/(app)/reports/page-fc84bb5176572a31.js","/_next/static/chunks/app/(app)/returns/page-b91bab31a8b5592a.js","/_next/static/chunks/app/(app)/sales/page-3d2d4f1fdeafaf09.js","/_next/static/chunks/app/(app)/settings/page-4d1f475a1d47d35c.js","/_next/static/chunks/app/(app)/subscription/page-3ec42c2eca47cc15.js","/_next/static/chunks/app/(app)/supplier-records/page-1f1771f746f0c9a3.js","/_next/static/chunks/app/(app)/users/detail/page-f27834c1f5e0c1eb.js","/_next/static/chunks/app/(app)/users/page-54a51387c8cd4519.js","/_next/static/chunks/app/(app)/web-orders/page-641b4dc3e5be7c1f.js","/_next/static/chunks/app/(app)/website/page-ca96cd1d46062f31.js","/_next/static/chunks/app/(marketing)/compare/[slug]/page-6e006a96f690ab9c.js","/_next/static/chunks/app/(marketing)/en/compare/[slug]/page-8855a2f062e88f57.js","/_next/static/chunks/app/(marketing)/en/guides/[slug]/page-2ad80162d018b1b2.js","/_next/static/chunks/app/(marketing)/en/guides/page-17d52ecd79da61ab.js","/_next/static/chunks/app/(marketing)/en/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/en/page-ed19070043650d3b.js","/_next/static/chunks/app/(marketing)/en/pricing/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/en/pricing/page-f5f4eecc31be204f.js","/_next/static/chunks/app/(marketing)/en/product/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/en/product/page-bc86875b1960e57f.js","/_next/static/chunks/app/(marketing)/en/register/hosting/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/en/register/hosting/page-97efc57948380fcc.js","/_next/static/chunks/app/(marketing)/en/register/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/en/register/page-6c65bc904ca1473e.js","/_next/static/chunks/app/(marketing)/en/solutions/[slug]/page-10fa3d5130e5a6b6.js","/_next/static/chunks/app/(marketing)/en/solutions/page-8180d80d9ec70d10.js","/_next/static/chunks/app/(marketing)/guides/[slug]/page-68dd361f6ff3da3d.js","/_next/static/chunks/app/(marketing)/guides/page-e5f68a0585ed14d8.js","/_next/static/chunks/app/(marketing)/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/page-3e947d4fa60be63e.js","/_next/static/chunks/app/(marketing)/pricing/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/pricing/page-571894eb77c3d967.js","/_next/static/chunks/app/(marketing)/product/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/product/page-f4430d210a1ecfdd.js","/_next/static/chunks/app/(marketing)/register/hosting/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/register/hosting/page-b9286dce2d6227d1.js","/_next/static/chunks/app/(marketing)/register/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/register/page-8a76d8f162862004.js","/_next/static/chunks/app/(marketing)/solutions/[slug]/page-aedebd045254ce23.js","/_next/static/chunks/app/(marketing)/solutions/page-a4023d0a016da381.js","/_next/static/chunks/app/_not-found/page-93f5ecd9b5a1b8d5.js","/_next/static/chunks/app/activate-owner/layout-163c837417bd2db7.js","/_next/static/chunks/app/activate-owner/page-3196bd1b33111d46.js","/_next/static/chunks/app/forgot-password/layout-163c837417bd2db7.js","/_next/static/chunks/app/forgot-password/page-c61e97e651743b80.js","/_next/static/chunks/app/layout-3828c5e56ac03f65.js","/_next/static/chunks/app/login/layout-163c837417bd2db7.js","/_next/static/chunks/app/login/page-175a547e03d84015.js","/_next/static/chunks/app/reset-password/layout-163c837417bd2db7.js","/_next/static/chunks/app/reset-password/page-00e0cf959dc534b1.js","/_next/static/chunks/app/robots.txt/route-163c837417bd2db7.js","/_next/static/chunks/app/sitemap.xml/route-163c837417bd2db7.js","/_next/static/chunks/framework-ac871cde7d705c3a.js","/_next/static/chunks/main-61969269e7b3dad5.js","/_next/static/chunks/main-app-d3c2614b980cfab3.js","/_next/static/chunks/pages/_app-c0e3f7ff6ef43cb0.js","/_next/static/chunks/pages/_error-6bf3d2bf6fe2d033.js","/_next/static/chunks/polyfills-42372ed130431b0a.js","/_next/static/chunks/webpack-8e3c99ca2bb1234e.js","/_next/static/css/d58e0e2079745c13.css","/_next/static/media/011e180705008d6f-s.woff2","/_next/static/media/01f0c602c274ea55-s.woff2","/_next/static/media/19cfc7226ec3afaa-s.woff2","/_next/static/media/1ebb550cd0a67fc6-s.p.woff2","/_next/static/media/21350d82a1f187e9-s.woff2","/_next/static/media/350b852752f8489d-s.p.woff2","/_next/static/media/3dc379dc9b5dec12-s.p.woff2","/_next/static/media/58f386aa6b1a2a92-s.woff2","/_next/static/media/5ec84f17416dda4d-s.woff2","/_next/static/media/63a79a6cf340c5d2-s.p.woff2","/_next/static/media/7ba5fb2a8c88521c-s.woff2","/_next/static/media/8e9860b6e62d6359-s.woff2","/_next/static/media/92eeb95d069020cc-s.woff2","/_next/static/media/98e207f02528a563-s.p.woff2","/_next/static/media/99dcf268bda04fe5-s.woff2","/_next/static/media/ba9851c3c22cd980-s.woff2","/_next/static/media/c5f10e9e72d35c52-s.woff2","/_next/static/media/c5fe6dc8356a8c31-s.woff2","/_next/static/media/ce401babc0566bc1-s.woff2","/_next/static/media/d29838c109ef09b4-s.woff2","/_next/static/media/d3ebbfd689654d3a-s.p.woff2","/_next/static/media/dd994fbf464986f0-s.p.woff2","/_next/static/media/df0a9ae256c0569c-s.woff2","/_next/static/media/e40af3453d7c920a-s.woff2","/_next/static/media/e4af272ccee01ff0-s.p.woff2","/_next/static/media/e97026df054cf2a3-s.woff2","/_next/static/media/ef4d5661765d0e49-s.woff2","/_next/static/media/f15f45d13243c643-s.woff2","/icons/apple-touch-icon.png","/icons/icon-192.png","/icons/icon-512.png","/icons/icon-maskable-192.png","/icons/icon-maskable-512.png","/manifest.webmanifest"];
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
