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
const BUILD = "4etizlpXK1XHnqq_9z1mw";
const CACHE = `vezano-shell-${BUILD}`;
// Every screen of the app, so the person lands on the page they asked for
// with no network — never on a different one. Filled in at build time from
// the export; the list below is the floor the PWA manifest relies on.
const PRECACHE_PAGES = ["/", "/login/", "/dashboard/", "/sales/", "/inventory/", "/returns/"];
const PRECACHE_APP_PAGES = ["/activate-owner/","/crm/","/customer-records/","/dashboard/","/debts/","/finance/","/forgot-password/","/hr/","/inventory/","/labels/","/login/","/logs/","/org/","/platform-activity/","/platform-analytics/","/platform-companies/","/platform-errors/","/platform-finance/","/platform-leads/","/platform-plans/","/platform-registrations/","/platform-seo/","/platform-subscriptions/","/platform-team/","/platform-team/member/","/platform/","/purchasing/","/reports/","/reset-password/","/returns/","/sales/","/settings/","/subscription/","/supplier-records/","/track/","/users/","/users/detail/","/web-orders/","/website/"];
// Every hashed chunk, stylesheet and font of this build, plus the manifest
// and icons — filled in at build time from the export.
const PRECACHE_ASSETS = ["/_next/static/4etizlpXK1XHnqq_9z1mw/_buildManifest.js","/_next/static/4etizlpXK1XHnqq_9z1mw/_ssgManifest.js","/_next/static/chunks/1328-f61aca8e87377237.js","/_next/static/chunks/1391-0b93ee9d9f7c21e5.js","/_next/static/chunks/1409-576fc5d9bffa166d.js","/_next/static/chunks/1629-90ae536668099642.js","/_next/static/chunks/2126-637036f8cf192429.js","/_next/static/chunks/2395-f405d986edddf4c1.js","/_next/static/chunks/2785-e5f6354b21f45a4e.js","/_next/static/chunks/2901-9378a76108e8dd11.js","/_next/static/chunks/3117-779e968607fe2cc6.js","/_next/static/chunks/3415-b951caf019ae8be7.js","/_next/static/chunks/3995-193cf33b08e91925.js","/_next/static/chunks/4023-b289b6ac0ec1eb95.js","/_next/static/chunks/40b91c18-03576e02c01e0947.js","/_next/static/chunks/4200-086e4dd05ced843c.js","/_next/static/chunks/4265-6b8e540634aefe6a.js","/_next/static/chunks/4473-8ea572ad178595e9.js","/_next/static/chunks/476-715cb53b79f2ea8a.js","/_next/static/chunks/4838-398c296d08c00313.js","/_next/static/chunks/5405.a2853eec62072dae.js","/_next/static/chunks/5410-087bc64c21c04d17.js","/_next/static/chunks/5479-c96fa33911fa3aa4.js","/_next/static/chunks/602-03405589c9d1b4cb.js","/_next/static/chunks/6702-5a33da0ccd8afcac.js","/_next/static/chunks/689-3a975c32e6f17e88.js","/_next/static/chunks/694-73d22f93c292b472.js","/_next/static/chunks/7536-15fbefc9cc695446.js","/_next/static/chunks/7769-313f6fad97c64c58.js","/_next/static/chunks/7985-483de8706fec7093.js","/_next/static/chunks/8117-220f357cdf1dced1.js","/_next/static/chunks/8199-3642ce5e9c37057a.js","/_next/static/chunks/8288-b9c440ad175c3696.js","/_next/static/chunks/8430-f929184bb61c728a.js","/_next/static/chunks/8441-2d584939c09e33d5.js","/_next/static/chunks/8557.2b38635e6f604328.js","/_next/static/chunks/8890-8d55eed9baf2240c.js","/_next/static/chunks/9242-05d63c0a823b25ca.js","/_next/static/chunks/9681-ee25e157d65fdbb4.js","/_next/static/chunks/9865-083a76278b913e92.js","/_next/static/chunks/app/(app)/crm/page-4a1978ac744e8fec.js","/_next/static/chunks/app/(app)/customer-records/page-a83bae66499ea273.js","/_next/static/chunks/app/(app)/dashboard/page-a6d31b7460705ad2.js","/_next/static/chunks/app/(app)/debts/page-ca0ed3aa011d9020.js","/_next/static/chunks/app/(app)/finance/page-34b7583670f6baf9.js","/_next/static/chunks/app/(app)/hr/page-b14e09649e55d219.js","/_next/static/chunks/app/(app)/inventory/page-c2c6588a23c712b1.js","/_next/static/chunks/app/(app)/labels/page-6f2882af349b12e5.js","/_next/static/chunks/app/(app)/layout-c327639cc9df5a2d.js","/_next/static/chunks/app/(app)/logs/page-3e571aa6c274840b.js","/_next/static/chunks/app/(app)/org/page-ee7fbcef4114f6d0.js","/_next/static/chunks/app/(app)/platform-activity/page-afa8aca0bc9d4880.js","/_next/static/chunks/app/(app)/platform-analytics/page-022d47f30a35c7b8.js","/_next/static/chunks/app/(app)/platform-companies/page-f810ac5065838f5d.js","/_next/static/chunks/app/(app)/platform-errors/page-6d9f8d79d69c4067.js","/_next/static/chunks/app/(app)/platform-finance/page-311c74c60643acc4.js","/_next/static/chunks/app/(app)/platform-leads/page-8fe956efa440e0b7.js","/_next/static/chunks/app/(app)/platform-plans/page-d7df628d3af678c5.js","/_next/static/chunks/app/(app)/platform-registrations/page-405fc3ef0ca00f94.js","/_next/static/chunks/app/(app)/platform-seo/page-a1a3451c48ef4779.js","/_next/static/chunks/app/(app)/platform-subscriptions/page-5a00f14e283c384d.js","/_next/static/chunks/app/(app)/platform-team/member/page-3b4ba8ce083385a8.js","/_next/static/chunks/app/(app)/platform-team/page-518a6c4ef48546dd.js","/_next/static/chunks/app/(app)/platform/page-c3f85d939866cc25.js","/_next/static/chunks/app/(app)/purchasing/page-5cb9a6f2c84ed473.js","/_next/static/chunks/app/(app)/reports/page-84076628c4e04b8f.js","/_next/static/chunks/app/(app)/returns/page-c755470adb211c2f.js","/_next/static/chunks/app/(app)/sales/page-589a5ab51d4c6f76.js","/_next/static/chunks/app/(app)/settings/page-ca595f089ebb02ae.js","/_next/static/chunks/app/(app)/subscription/page-bbffede16a0db964.js","/_next/static/chunks/app/(app)/supplier-records/page-2cddcae51039b896.js","/_next/static/chunks/app/(app)/users/detail/page-b778245dd4bd95cf.js","/_next/static/chunks/app/(app)/users/page-d900f38333a90e29.js","/_next/static/chunks/app/(app)/web-orders/page-1adc9f60378c4c2a.js","/_next/static/chunks/app/(app)/website/page-f9240a6bc5e5e823.js","/_next/static/chunks/app/(marketing)/compare/[slug]/page-a968478cd53751af.js","/_next/static/chunks/app/(marketing)/en/compare/[slug]/page-5d6550dd8599ea9b.js","/_next/static/chunks/app/(marketing)/en/guides/[slug]/page-b813e6311dc4f724.js","/_next/static/chunks/app/(marketing)/en/guides/page-32e655588f92f1ab.js","/_next/static/chunks/app/(marketing)/en/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/en/page-9063500e8baf509d.js","/_next/static/chunks/app/(marketing)/en/pricing/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/en/pricing/page-6ebad3ff91e36711.js","/_next/static/chunks/app/(marketing)/en/product/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/en/product/page-00bd1f7ce76869d9.js","/_next/static/chunks/app/(marketing)/en/register/hosting/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/en/register/hosting/page-9738ac0ce1a80971.js","/_next/static/chunks/app/(marketing)/en/register/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/en/register/page-ea4f2ff18590d53c.js","/_next/static/chunks/app/(marketing)/en/solutions/[slug]/page-9f82ae6047c5c5ce.js","/_next/static/chunks/app/(marketing)/en/solutions/page-a836e63114d84088.js","/_next/static/chunks/app/(marketing)/en/track/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/en/track/page-fdcc8f681c0220ea.js","/_next/static/chunks/app/(marketing)/guides/[slug]/page-5b27be70b0e722d3.js","/_next/static/chunks/app/(marketing)/guides/page-dc11a4d0fcd2c978.js","/_next/static/chunks/app/(marketing)/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/page-4759f4868747bda8.js","/_next/static/chunks/app/(marketing)/pricing/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/pricing/page-50edf9474f30fc05.js","/_next/static/chunks/app/(marketing)/product/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/product/page-143dbb7c0142dfca.js","/_next/static/chunks/app/(marketing)/register/hosting/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/register/hosting/page-9ed9ef8aebeebad0.js","/_next/static/chunks/app/(marketing)/register/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/register/page-d7b0446f0f87b55d.js","/_next/static/chunks/app/(marketing)/solutions/[slug]/page-c3ef68e851b73d3e.js","/_next/static/chunks/app/(marketing)/solutions/page-eb3652250f07fbe3.js","/_next/static/chunks/app/(marketing)/track/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/track/page-766ea09bcabf9fa9.js","/_next/static/chunks/app/_not-found/page-93f5ecd9b5a1b8d5.js","/_next/static/chunks/app/activate-owner/layout-9111370ccccd4922.js","/_next/static/chunks/app/activate-owner/page-c8187e50fad3c246.js","/_next/static/chunks/app/forgot-password/layout-9111370ccccd4922.js","/_next/static/chunks/app/forgot-password/page-76dc47d1c55a5c4f.js","/_next/static/chunks/app/layout-29446a39bb22ddbe.js","/_next/static/chunks/app/login/layout-9111370ccccd4922.js","/_next/static/chunks/app/login/page-edb2961cce0a53fd.js","/_next/static/chunks/app/reset-password/layout-9111370ccccd4922.js","/_next/static/chunks/app/reset-password/page-995b4e5a904f1078.js","/_next/static/chunks/app/robots.txt/route-9111370ccccd4922.js","/_next/static/chunks/app/sitemap.xml/route-9111370ccccd4922.js","/_next/static/chunks/framework-ac871cde7d705c3a.js","/_next/static/chunks/main-61969269e7b3dad5.js","/_next/static/chunks/main-app-d3c2614b980cfab3.js","/_next/static/chunks/pages/_app-c0e3f7ff6ef43cb0.js","/_next/static/chunks/pages/_error-6bf3d2bf6fe2d033.js","/_next/static/chunks/polyfills-42372ed130431b0a.js","/_next/static/chunks/webpack-b9d10a9d6c5c314a.js","/_next/static/css/b0b1eb5ca07a8903.css","/_next/static/media/011e180705008d6f-s.woff2","/_next/static/media/19cfc7226ec3afaa-s.woff2","/_next/static/media/1ebb550cd0a67fc6-s.p.woff2","/_next/static/media/21350d82a1f187e9-s.woff2","/_next/static/media/3dc379dc9b5dec12-s.p.woff2","/_next/static/media/58c726479f69cacd-s.woff2","/_next/static/media/58f386aa6b1a2a92-s.woff2","/_next/static/media/63a79a6cf340c5d2-s.p.woff2","/_next/static/media/7ba5fb2a8c88521c-s.woff2","/_next/static/media/8e9860b6e62d6359-s.woff2","/_next/static/media/92eeb95d069020cc-s.woff2","/_next/static/media/98e207f02528a563-s.p.woff2","/_next/static/media/99dcf268bda04fe5-s.woff2","/_next/static/media/ba9851c3c22cd980-s.woff2","/_next/static/media/bd9c8c62ffadd9dd-s.p.woff2","/_next/static/media/c5f10e9e72d35c52-s.woff2","/_next/static/media/c5fe6dc8356a8c31-s.woff2","/_next/static/media/cc8b755e9c1ba115-s.woff2","/_next/static/media/ce401babc0566bc1-s.woff2","/_next/static/media/d29838c109ef09b4-s.woff2","/_next/static/media/d3ebbfd689654d3a-s.p.woff2","/_next/static/media/dd994fbf464986f0-s.p.woff2","/_next/static/media/df0a9ae256c0569c-s.woff2","/_next/static/media/e40af3453d7c920a-s.woff2","/_next/static/media/e4af272ccee01ff0-s.p.woff2","/_next/static/media/e97026df054cf2a3-s.woff2","/_next/static/media/ef4d5661765d0e49-s.woff2","/_next/static/media/f15f45d13243c643-s.woff2","/_next/static/media/f952393b67d608ec-s.p.woff2","/icons/apple-touch-icon.png","/icons/badge-96.png","/icons/icon-192.png","/icons/icon-512.png","/icons/icon-maskable-192.png","/icons/icon-maskable-512.png","/manifest.webmanifest"];
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
