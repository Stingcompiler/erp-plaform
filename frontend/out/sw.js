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
const BUILD = "8HHRPRPqMQX1nyT6d-2vh";
const CACHE = `vezano-shell-${BUILD}`;
// Every screen of the app, so the person lands on the page they asked for
// with no network — never on a different one. Filled in at build time from
// the export; the list below is the floor the PWA manifest relies on.
const PRECACHE_PAGES = ["/", "/login/", "/dashboard/", "/sales/", "/inventory/", "/returns/"];
const PRECACHE_APP_PAGES = ["/activate-owner/","/crm/","/customer-records/","/dashboard/","/debts/","/finance/","/forgot-password/","/hr/","/inventory/","/labels/","/login/","/logs/","/org/","/platform-activity/","/platform-analytics/","/platform-companies/","/platform-errors/","/platform-finance/","/platform-leads/","/platform-plans/","/platform-registrations/","/platform-seo/","/platform-subscriptions/","/platform-team/","/platform-team/member/","/platform/","/purchasing/","/reports/","/reset-password/","/returns/","/sales/","/settings/","/subscription/","/supplier-records/","/users/","/users/detail/","/web-orders/","/website/"];
// Every hashed chunk, stylesheet and font of this build, plus the manifest
// and icons — filled in at build time from the export.
const PRECACHE_ASSETS = ["/_next/static/8HHRPRPqMQX1nyT6d-2vh/_buildManifest.js","/_next/static/8HHRPRPqMQX1nyT6d-2vh/_ssgManifest.js","/_next/static/chunks/1391-0b93ee9d9f7c21e5.js","/_next/static/chunks/1801-7e61d58fc5519497.js","/_next/static/chunks/2126-d582a29a57782664.js","/_next/static/chunks/2127-dc6abf93775fe235.js","/_next/static/chunks/2220-28c95603ac346713.js","/_next/static/chunks/2395-2840df6565c7c063.js","/_next/static/chunks/2901-401f1a92695f4c98.js","/_next/static/chunks/3106-dc54beff2352305c.js","/_next/static/chunks/3411-d39748328d8b17ac.js","/_next/static/chunks/3415-cb035e996443ebc6.js","/_next/static/chunks/3902-22f25e9dffa5bfea.js","/_next/static/chunks/3995-193cf33b08e91925.js","/_next/static/chunks/40b91c18-03576e02c01e0947.js","/_next/static/chunks/4200-086e4dd05ced843c.js","/_next/static/chunks/4265-4b9c0eb9f5971919.js","/_next/static/chunks/4473-acbbb3b1e30980db.js","/_next/static/chunks/4686-8fa08f958a84bae2.js","/_next/static/chunks/4838-08aa2a9484c8a67a.js","/_next/static/chunks/5127-8ce8e51bca0fc7a3.js","/_next/static/chunks/5270-fd78028256dbaba0.js","/_next/static/chunks/5405.a2853eec62072dae.js","/_next/static/chunks/5410-087bc64c21c04d17.js","/_next/static/chunks/5850-bba505c71ea8b9e4.js","/_next/static/chunks/6472-6ce7a3cce4a6401b.js","/_next/static/chunks/6702-5a33da0ccd8afcac.js","/_next/static/chunks/7655-eff8438d163b666c.js","/_next/static/chunks/7670-1056d442efeb12ab.js","/_next/static/chunks/7769-313f6fad97c64c58.js","/_next/static/chunks/8117-7b8cad2342bec1fa.js","/_next/static/chunks/8430-f929184bb61c728a.js","/_next/static/chunks/app/(app)/crm/page-aebc20dffbeead0e.js","/_next/static/chunks/app/(app)/customer-records/page-207e8dfbdb7eea47.js","/_next/static/chunks/app/(app)/dashboard/page-be92c41cf0791b3f.js","/_next/static/chunks/app/(app)/debts/page-72e8ea0a3bc9653b.js","/_next/static/chunks/app/(app)/finance/page-f60ca62e7bd784d5.js","/_next/static/chunks/app/(app)/hr/page-9be7ef909fa75a3f.js","/_next/static/chunks/app/(app)/inventory/page-e3aeb2265247d6ad.js","/_next/static/chunks/app/(app)/labels/page-3c84b644716b1f7f.js","/_next/static/chunks/app/(app)/layout-3b7afb82042e008d.js","/_next/static/chunks/app/(app)/logs/page-6834769a01f7740e.js","/_next/static/chunks/app/(app)/org/page-5d28c1beffbc6c3e.js","/_next/static/chunks/app/(app)/platform-activity/page-ce0e74d5128f4b6e.js","/_next/static/chunks/app/(app)/platform-analytics/page-63bafe2e3fe13d79.js","/_next/static/chunks/app/(app)/platform-companies/page-3f9aa9b37aad644c.js","/_next/static/chunks/app/(app)/platform-errors/page-3e42e7512f12845a.js","/_next/static/chunks/app/(app)/platform-finance/page-cab86745a720242e.js","/_next/static/chunks/app/(app)/platform-leads/page-0c9f72317368b89a.js","/_next/static/chunks/app/(app)/platform-plans/page-909648d8117ceaed.js","/_next/static/chunks/app/(app)/platform-registrations/page-2438c50ca276018b.js","/_next/static/chunks/app/(app)/platform-seo/page-7690bc436d1d9994.js","/_next/static/chunks/app/(app)/platform-subscriptions/page-8244a8baab365088.js","/_next/static/chunks/app/(app)/platform-team/member/page-f853bc88ed6c9314.js","/_next/static/chunks/app/(app)/platform-team/page-ea4ba8b59ef50a96.js","/_next/static/chunks/app/(app)/platform/page-8ae3e02456cc9a1e.js","/_next/static/chunks/app/(app)/purchasing/page-7e3a0110e5dc4421.js","/_next/static/chunks/app/(app)/reports/page-81065f2ce8913b0d.js","/_next/static/chunks/app/(app)/returns/page-70b9fcbb64a8db7a.js","/_next/static/chunks/app/(app)/sales/page-93cc8dda305d86bc.js","/_next/static/chunks/app/(app)/settings/page-1c2e592acd7c518b.js","/_next/static/chunks/app/(app)/subscription/page-3be5b22b76259917.js","/_next/static/chunks/app/(app)/supplier-records/page-0e71c091e788049f.js","/_next/static/chunks/app/(app)/users/detail/page-55b3cfbe56460fbe.js","/_next/static/chunks/app/(app)/users/page-37f29fd36485c035.js","/_next/static/chunks/app/(app)/web-orders/page-32b76c3d173695d5.js","/_next/static/chunks/app/(app)/website/page-1e481cf87907acf5.js","/_next/static/chunks/app/(marketing)/compare/[slug]/page-11cdc3bb0acdbb2d.js","/_next/static/chunks/app/(marketing)/en/compare/[slug]/page-6a6d3f6007d1e49d.js","/_next/static/chunks/app/(marketing)/en/guides/[slug]/page-8bf71386f2e0e33a.js","/_next/static/chunks/app/(marketing)/en/guides/page-cd0de8fa0a850c33.js","/_next/static/chunks/app/(marketing)/en/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/en/page-eba38b65660db076.js","/_next/static/chunks/app/(marketing)/en/pricing/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/en/pricing/page-6cb5d6597a200e9a.js","/_next/static/chunks/app/(marketing)/en/product/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/en/product/page-83651b0b6e768e63.js","/_next/static/chunks/app/(marketing)/en/register/hosting/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/en/register/hosting/page-201058b5be654053.js","/_next/static/chunks/app/(marketing)/en/register/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/en/register/page-d12002294a039a22.js","/_next/static/chunks/app/(marketing)/en/solutions/[slug]/page-d5ee8a5c01222c17.js","/_next/static/chunks/app/(marketing)/en/solutions/page-4da64ba9e2f65c92.js","/_next/static/chunks/app/(marketing)/guides/[slug]/page-b1dabf8dd35facd3.js","/_next/static/chunks/app/(marketing)/guides/page-96207b355d8fd2d8.js","/_next/static/chunks/app/(marketing)/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/page-8fb5428f96d5472b.js","/_next/static/chunks/app/(marketing)/pricing/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/pricing/page-97fb30d7a565303f.js","/_next/static/chunks/app/(marketing)/product/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/product/page-c550ed1657df4b26.js","/_next/static/chunks/app/(marketing)/register/hosting/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/register/hosting/page-d1e78436b7439ab5.js","/_next/static/chunks/app/(marketing)/register/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/register/page-0caa5428ea15b304.js","/_next/static/chunks/app/(marketing)/solutions/[slug]/page-15217b40a1ef0550.js","/_next/static/chunks/app/(marketing)/solutions/page-92ecc9cefcb92ab8.js","/_next/static/chunks/app/_not-found/page-93f5ecd9b5a1b8d5.js","/_next/static/chunks/app/activate-owner/layout-163c837417bd2db7.js","/_next/static/chunks/app/activate-owner/page-5d1c00b8e594e5b4.js","/_next/static/chunks/app/forgot-password/layout-163c837417bd2db7.js","/_next/static/chunks/app/forgot-password/page-24c7d3c1ea2912ac.js","/_next/static/chunks/app/layout-6ca83f5dd1269269.js","/_next/static/chunks/app/login/layout-163c837417bd2db7.js","/_next/static/chunks/app/login/page-a9968e3dea10ba39.js","/_next/static/chunks/app/reset-password/layout-163c837417bd2db7.js","/_next/static/chunks/app/reset-password/page-1aa11d3281905a0f.js","/_next/static/chunks/app/robots.txt/route-163c837417bd2db7.js","/_next/static/chunks/app/sitemap.xml/route-163c837417bd2db7.js","/_next/static/chunks/framework-ac871cde7d705c3a.js","/_next/static/chunks/main-61969269e7b3dad5.js","/_next/static/chunks/main-app-d3c2614b980cfab3.js","/_next/static/chunks/pages/_app-c0e3f7ff6ef43cb0.js","/_next/static/chunks/pages/_error-6bf3d2bf6fe2d033.js","/_next/static/chunks/polyfills-42372ed130431b0a.js","/_next/static/chunks/webpack-8e3c99ca2bb1234e.js","/_next/static/css/c64c0353fd091f6c.css","/_next/static/media/011e180705008d6f-s.woff2","/_next/static/media/01f0c602c274ea55-s.woff2","/_next/static/media/19cfc7226ec3afaa-s.woff2","/_next/static/media/1ebb550cd0a67fc6-s.p.woff2","/_next/static/media/21350d82a1f187e9-s.woff2","/_next/static/media/350b852752f8489d-s.p.woff2","/_next/static/media/3dc379dc9b5dec12-s.p.woff2","/_next/static/media/58f386aa6b1a2a92-s.woff2","/_next/static/media/5ec84f17416dda4d-s.woff2","/_next/static/media/63a79a6cf340c5d2-s.p.woff2","/_next/static/media/7ba5fb2a8c88521c-s.woff2","/_next/static/media/8e9860b6e62d6359-s.woff2","/_next/static/media/92eeb95d069020cc-s.woff2","/_next/static/media/98e207f02528a563-s.p.woff2","/_next/static/media/99dcf268bda04fe5-s.woff2","/_next/static/media/ba9851c3c22cd980-s.woff2","/_next/static/media/c5f10e9e72d35c52-s.woff2","/_next/static/media/c5fe6dc8356a8c31-s.woff2","/_next/static/media/ce401babc0566bc1-s.woff2","/_next/static/media/d29838c109ef09b4-s.woff2","/_next/static/media/d3ebbfd689654d3a-s.p.woff2","/_next/static/media/dd994fbf464986f0-s.p.woff2","/_next/static/media/df0a9ae256c0569c-s.woff2","/_next/static/media/e40af3453d7c920a-s.woff2","/_next/static/media/e4af272ccee01ff0-s.p.woff2","/_next/static/media/e97026df054cf2a3-s.woff2","/_next/static/media/ef4d5661765d0e49-s.woff2","/_next/static/media/f15f45d13243c643-s.woff2","/icons/apple-touch-icon.png","/icons/icon-192.png","/icons/icon-512.png","/icons/icon-maskable-192.png","/icons/icon-maskable-512.png","/manifest.webmanifest"];
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
