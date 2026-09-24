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
const BUILD = "y38_VOORn8trnCTbU2R-C";
const CACHE = `vezano-shell-${BUILD}`;
// Every screen of the app, so the person lands on the page they asked for
// with no network — never on a different one. Filled in at build time from
// the export; the list below is the floor the PWA manifest relies on.
const PRECACHE_PAGES = ["/", "/login/", "/dashboard/", "/sales/", "/inventory/", "/returns/"];
const PRECACHE_APP_PAGES = ["/activate-owner/","/crm/","/customer-records/","/dashboard/","/debts/","/finance/","/forgot-password/","/hr/","/inventory/","/labels/","/login/","/logs/","/org/","/platform-activity/","/platform-analytics/","/platform-companies/","/platform-errors/","/platform-finance/","/platform-leads/","/platform-plans/","/platform-registrations/","/platform-seo/","/platform-subscriptions/","/platform-team/","/platform-team/member/","/platform/","/purchasing/","/reports/","/reset-password/","/returns/","/sales/","/settings/","/subscription/","/supplier-records/","/users/","/users/detail/","/web-orders/","/website/"];
// Every hashed chunk, stylesheet and font of this build, plus the manifest
// and icons — filled in at build time from the export.
const PRECACHE_ASSETS = ["/_next/static/chunks/1391-0b93ee9d9f7c21e5.js","/_next/static/chunks/1801-7e61d58fc5519497.js","/_next/static/chunks/2127-dc6abf93775fe235.js","/_next/static/chunks/2220-28c95603ac346713.js","/_next/static/chunks/2395-2840df6565c7c063.js","/_next/static/chunks/2901-401f1a92695f4c98.js","/_next/static/chunks/3106-dc54beff2352305c.js","/_next/static/chunks/3415-1e2bcd7db8d04b59.js","/_next/static/chunks/3902-22f25e9dffa5bfea.js","/_next/static/chunks/3995-193cf33b08e91925.js","/_next/static/chunks/40b91c18-03576e02c01e0947.js","/_next/static/chunks/4200-086e4dd05ced843c.js","/_next/static/chunks/4265-4b9c0eb9f5971919.js","/_next/static/chunks/4473-acbbb3b1e30980db.js","/_next/static/chunks/4686-63ed42d57070ce0c.js","/_next/static/chunks/4838-e77e854c77d4f670.js","/_next/static/chunks/4878-df35a09aad37a893.js","/_next/static/chunks/5127-f32ff916a49297d5.js","/_next/static/chunks/5270-bbb95e5f3a6afaf1.js","/_next/static/chunks/5405.6b9d8c3845e2492a.js","/_next/static/chunks/5410-087bc64c21c04d17.js","/_next/static/chunks/5850-bba505c71ea8b9e4.js","/_next/static/chunks/6472-6ce7a3cce4a6401b.js","/_next/static/chunks/6702-5a33da0ccd8afcac.js","/_next/static/chunks/7655-eff8438d163b666c.js","/_next/static/chunks/7670-1056d442efeb12ab.js","/_next/static/chunks/7769-313f6fad97c64c58.js","/_next/static/chunks/8117-7b8cad2342bec1fa.js","/_next/static/chunks/8430-f929184bb61c728a.js","/_next/static/chunks/9039-b5601357c80f490b.js","/_next/static/chunks/app/(app)/crm/page-4bade2805b6d560f.js","/_next/static/chunks/app/(app)/customer-records/page-e78addc3c8951860.js","/_next/static/chunks/app/(app)/dashboard/page-69327518ae9ec86f.js","/_next/static/chunks/app/(app)/debts/page-e5358da924fa2165.js","/_next/static/chunks/app/(app)/finance/page-06c0c352c11f751d.js","/_next/static/chunks/app/(app)/hr/page-08360c6218bf01f6.js","/_next/static/chunks/app/(app)/inventory/page-153b8152c84de212.js","/_next/static/chunks/app/(app)/labels/page-205146a3daf48076.js","/_next/static/chunks/app/(app)/layout-c847d8dc909599de.js","/_next/static/chunks/app/(app)/logs/page-59f015707c8adf5e.js","/_next/static/chunks/app/(app)/org/page-b11b6b72bf9d1f1f.js","/_next/static/chunks/app/(app)/platform-activity/page-f8e5f4f30add61a2.js","/_next/static/chunks/app/(app)/platform-analytics/page-f84a5ab237808046.js","/_next/static/chunks/app/(app)/platform-companies/page-00881c736cad2dbd.js","/_next/static/chunks/app/(app)/platform-errors/page-dd3fb34182448e1d.js","/_next/static/chunks/app/(app)/platform-finance/page-4411e4e93a4f2167.js","/_next/static/chunks/app/(app)/platform-leads/page-a4147e525fb15d90.js","/_next/static/chunks/app/(app)/platform-plans/page-8abc5781e6c00d88.js","/_next/static/chunks/app/(app)/platform-registrations/page-2bdec49c5462132b.js","/_next/static/chunks/app/(app)/platform-seo/page-ca62dfb566e00934.js","/_next/static/chunks/app/(app)/platform-subscriptions/page-34666f026649b83f.js","/_next/static/chunks/app/(app)/platform-team/member/page-44de2138dc71d0ff.js","/_next/static/chunks/app/(app)/platform-team/page-3bcc466fa60077ec.js","/_next/static/chunks/app/(app)/platform/page-2d5a1ad7424a68e3.js","/_next/static/chunks/app/(app)/purchasing/page-ee7150c81c5e02c7.js","/_next/static/chunks/app/(app)/reports/page-3a270dfb32c99749.js","/_next/static/chunks/app/(app)/returns/page-807dbf582752a071.js","/_next/static/chunks/app/(app)/sales/page-5fcbd2b361fcc6e8.js","/_next/static/chunks/app/(app)/settings/page-2cb95e8b82714160.js","/_next/static/chunks/app/(app)/subscription/page-680a7c49b186045a.js","/_next/static/chunks/app/(app)/supplier-records/page-f2d6e063b56106a7.js","/_next/static/chunks/app/(app)/users/detail/page-6628882404afc1c7.js","/_next/static/chunks/app/(app)/users/page-095294935088028e.js","/_next/static/chunks/app/(app)/web-orders/page-95b74cf6936862a4.js","/_next/static/chunks/app/(app)/website/page-4d8375c6fe472ed4.js","/_next/static/chunks/app/(marketing)/compare/[slug]/page-e8e9f8f71a50e63a.js","/_next/static/chunks/app/(marketing)/en/compare/[slug]/page-38071e5d3f4a0ef5.js","/_next/static/chunks/app/(marketing)/en/guides/[slug]/page-091bc25b5b563c82.js","/_next/static/chunks/app/(marketing)/en/guides/page-9ff4798535128405.js","/_next/static/chunks/app/(marketing)/en/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/en/page-c9d3fb7f7f4c4611.js","/_next/static/chunks/app/(marketing)/en/pricing/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/en/pricing/page-042219ae48dd492f.js","/_next/static/chunks/app/(marketing)/en/product/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/en/product/page-9fc56dc7be5006bb.js","/_next/static/chunks/app/(marketing)/en/register/hosting/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/en/register/hosting/page-020b91e8dde0cf79.js","/_next/static/chunks/app/(marketing)/en/register/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/en/register/page-82dfcec7d4c4bc6d.js","/_next/static/chunks/app/(marketing)/en/solutions/[slug]/page-747799eac780dd39.js","/_next/static/chunks/app/(marketing)/en/solutions/page-f18089e11d33b664.js","/_next/static/chunks/app/(marketing)/guides/[slug]/page-b000663b4f9a6931.js","/_next/static/chunks/app/(marketing)/guides/page-bd2d9316908e33d8.js","/_next/static/chunks/app/(marketing)/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/page-8b59e2f32d3f7c5e.js","/_next/static/chunks/app/(marketing)/pricing/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/pricing/page-c525c440e4562fdd.js","/_next/static/chunks/app/(marketing)/product/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/product/page-ff9cf5c1c1cfc128.js","/_next/static/chunks/app/(marketing)/register/hosting/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/register/hosting/page-ef07dd83cd2cff9f.js","/_next/static/chunks/app/(marketing)/register/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/register/page-bd0491b898a63c16.js","/_next/static/chunks/app/(marketing)/solutions/[slug]/page-6cd5daeb6c2dce2a.js","/_next/static/chunks/app/(marketing)/solutions/page-6cc00f6861374008.js","/_next/static/chunks/app/_not-found/page-93f5ecd9b5a1b8d5.js","/_next/static/chunks/app/activate-owner/layout-163c837417bd2db7.js","/_next/static/chunks/app/activate-owner/page-f0cd78d7be9e91e9.js","/_next/static/chunks/app/forgot-password/layout-163c837417bd2db7.js","/_next/static/chunks/app/forgot-password/page-776a9cfd879ed1de.js","/_next/static/chunks/app/layout-98be0241489683fa.js","/_next/static/chunks/app/login/layout-163c837417bd2db7.js","/_next/static/chunks/app/login/page-693dbb8d29d32fc8.js","/_next/static/chunks/app/reset-password/layout-163c837417bd2db7.js","/_next/static/chunks/app/reset-password/page-e3a61125dafcd015.js","/_next/static/chunks/app/robots.txt/route-163c837417bd2db7.js","/_next/static/chunks/app/sitemap.xml/route-163c837417bd2db7.js","/_next/static/chunks/framework-ac871cde7d705c3a.js","/_next/static/chunks/main-61969269e7b3dad5.js","/_next/static/chunks/main-app-d3c2614b980cfab3.js","/_next/static/chunks/pages/_app-c0e3f7ff6ef43cb0.js","/_next/static/chunks/pages/_error-6bf3d2bf6fe2d033.js","/_next/static/chunks/polyfills-42372ed130431b0a.js","/_next/static/chunks/webpack-076a034402f93b3f.js","/_next/static/css/7d876e664442c41a.css","/_next/static/media/011e180705008d6f-s.woff2","/_next/static/media/01f0c602c274ea55-s.woff2","/_next/static/media/19cfc7226ec3afaa-s.woff2","/_next/static/media/1ebb550cd0a67fc6-s.p.woff2","/_next/static/media/21350d82a1f187e9-s.woff2","/_next/static/media/350b852752f8489d-s.p.woff2","/_next/static/media/3dc379dc9b5dec12-s.p.woff2","/_next/static/media/58f386aa6b1a2a92-s.woff2","/_next/static/media/5ec84f17416dda4d-s.woff2","/_next/static/media/63a79a6cf340c5d2-s.p.woff2","/_next/static/media/7ba5fb2a8c88521c-s.woff2","/_next/static/media/8e9860b6e62d6359-s.woff2","/_next/static/media/92eeb95d069020cc-s.woff2","/_next/static/media/98e207f02528a563-s.p.woff2","/_next/static/media/99dcf268bda04fe5-s.woff2","/_next/static/media/ba9851c3c22cd980-s.woff2","/_next/static/media/c5f10e9e72d35c52-s.woff2","/_next/static/media/c5fe6dc8356a8c31-s.woff2","/_next/static/media/ce401babc0566bc1-s.woff2","/_next/static/media/d29838c109ef09b4-s.woff2","/_next/static/media/d3ebbfd689654d3a-s.p.woff2","/_next/static/media/dd994fbf464986f0-s.p.woff2","/_next/static/media/df0a9ae256c0569c-s.woff2","/_next/static/media/e40af3453d7c920a-s.woff2","/_next/static/media/e4af272ccee01ff0-s.p.woff2","/_next/static/media/e97026df054cf2a3-s.woff2","/_next/static/media/ef4d5661765d0e49-s.woff2","/_next/static/media/f15f45d13243c643-s.woff2","/_next/static/y38_VOORn8trnCTbU2R-C/_buildManifest.js","/_next/static/y38_VOORn8trnCTbU2R-C/_ssgManifest.js","/icons/apple-touch-icon.png","/icons/icon-192.png","/icons/icon-512.png","/icons/icon-maskable-192.png","/icons/icon-maskable-512.png","/manifest.webmanifest"];
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
