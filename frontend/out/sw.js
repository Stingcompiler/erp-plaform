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
const BUILD = "nrWoN064v2UiEfXMu3A2C";
const CACHE = `vezano-shell-${BUILD}`;
// Every screen of the app, so the person lands on the page they asked for
// with no network — never on a different one. Filled in at build time from
// the export; the list below is the floor the PWA manifest relies on.
const PRECACHE_PAGES = ["/", "/login/", "/dashboard/", "/sales/", "/inventory/", "/returns/"];
const PRECACHE_APP_PAGES = ["/activate-owner/","/crm/","/customer-records/","/dashboard/","/debts/","/finance/","/forgot-password/","/hr/","/inventory/","/labels/","/login/","/logs/","/org/","/platform-activity/","/platform-analytics/","/platform-companies/","/platform-errors/","/platform-finance/","/platform-leads/","/platform-plans/","/platform-registrations/","/platform-seo/","/platform-subscriptions/","/platform-team/","/platform-team/member/","/platform/","/purchasing/","/reports/","/reset-password/","/returns/","/sales/","/settings/","/subscription/","/supplier-records/","/track/","/users/","/users/detail/","/web-orders/","/website/"];
// Every hashed chunk, stylesheet and font of this build, plus the manifest
// and icons — filled in at build time from the export.
const PRECACHE_ASSETS = ["/_next/static/chunks/1052-13b3e4f691c9f175.js","/_next/static/chunks/1228-5dff63c581a7eb54.js","/_next/static/chunks/1255-f456c2191ed027a9.js","/_next/static/chunks/1268-1786688b4b28516e.js","/_next/static/chunks/1597-571d6d678f664d18.js","/_next/static/chunks/2196-ac60d927b0bdacbe.js","/_next/static/chunks/2262-622d36d512aacf00.js","/_next/static/chunks/2313-6421cd4109690bf9.js","/_next/static/chunks/2391.d0eed6031ed46fa3.js","/_next/static/chunks/2545-6b4320da853323ed.js","/_next/static/chunks/2738-d4eb2070ab9b954f.js","/_next/static/chunks/280-43d2951a75ccb567.js","/_next/static/chunks/2951-fdf649aa33daf87f.js","/_next/static/chunks/3098-821cc236025de83c.js","/_next/static/chunks/3302-ce8798291078326a.js","/_next/static/chunks/3388-f3819ab090331ebc.js","/_next/static/chunks/3607-9a71bb1b19cbd46f.js","/_next/static/chunks/4050-26da8ba3c8913050.js","/_next/static/chunks/4103-6cbeaa358cad477a.js","/_next/static/chunks/4121-12a73e2c06735b4a.js","/_next/static/chunks/4537-64e4163de10aa22b.js","/_next/static/chunks/4545-f516c64e572ac8dd.js","/_next/static/chunks/4796-ddc6021c16d1db57.js","/_next/static/chunks/4825-e6884ca77311ee88.js","/_next/static/chunks/4bd1b696-100b9d70ed4e49c1.js","/_next/static/chunks/5286-d8c6136b6c128f1b.js","/_next/static/chunks/5421.d04d2b84e94672b6.js","/_next/static/chunks/5708-f7063cb5d5f1ebdd.js","/_next/static/chunks/5869-eae871e95f51cf81.js","/_next/static/chunks/6208-cc467e7008e1c4fc.js","/_next/static/chunks/6941-5b4020943229663e.js","/_next/static/chunks/7289-ce2dea732489a2b2.js","/_next/static/chunks/7865-52eda843c908da3b.js","/_next/static/chunks/8053-d2f3d3aaa0ba56b3.js","/_next/static/chunks/8109.46238d46d534e00a.js","/_next/static/chunks/8130-ccb79f1c6ae59ebc.js","/_next/static/chunks/8992-ae8f7e3665b583ae.js","/_next/static/chunks/9179-ad48cfdc4475d65f.js","/_next/static/chunks/9285-3efffe997d8117f7.js","/_next/static/chunks/9989-d8537ffacc6bf84b.js","/_next/static/chunks/app/(app)/crm/page-e5a364213c05fa4f.js","/_next/static/chunks/app/(app)/customer-records/page-a977cdfad5bf40ba.js","/_next/static/chunks/app/(app)/dashboard/page-98b29708ea06f860.js","/_next/static/chunks/app/(app)/debts/page-04083d6087324032.js","/_next/static/chunks/app/(app)/finance/page-fa59ff2a1f042e39.js","/_next/static/chunks/app/(app)/hr/page-6e0f966f6db98b66.js","/_next/static/chunks/app/(app)/inventory/page-a5293bc62e897939.js","/_next/static/chunks/app/(app)/labels/page-0015bb3ee061c6d0.js","/_next/static/chunks/app/(app)/layout-b396f57955b28b98.js","/_next/static/chunks/app/(app)/logs/page-74b460948e6b453b.js","/_next/static/chunks/app/(app)/org/page-a75c6dd75496f146.js","/_next/static/chunks/app/(app)/platform-activity/page-3b0d21230bb0c418.js","/_next/static/chunks/app/(app)/platform-analytics/page-95e7163a73d1291a.js","/_next/static/chunks/app/(app)/platform-companies/page-aea2373a1848b1a8.js","/_next/static/chunks/app/(app)/platform-errors/page-dc11a18785a00678.js","/_next/static/chunks/app/(app)/platform-finance/page-48760b4efa2de36d.js","/_next/static/chunks/app/(app)/platform-leads/page-28f282e8d312b5ce.js","/_next/static/chunks/app/(app)/platform-plans/page-771f8c1bde33c59d.js","/_next/static/chunks/app/(app)/platform-registrations/page-fbb84f4339047284.js","/_next/static/chunks/app/(app)/platform-seo/page-e416d5e301240e96.js","/_next/static/chunks/app/(app)/platform-subscriptions/page-2e8f06d5ae71466d.js","/_next/static/chunks/app/(app)/platform-team/member/page-ee246563877dc4d5.js","/_next/static/chunks/app/(app)/platform-team/page-4ed1f41bdbad6c81.js","/_next/static/chunks/app/(app)/platform/page-231b308ef444642c.js","/_next/static/chunks/app/(app)/purchasing/page-69390c93e8012ddf.js","/_next/static/chunks/app/(app)/reports/page-e1319b391e04b178.js","/_next/static/chunks/app/(app)/returns/page-342bfe7a0432f7da.js","/_next/static/chunks/app/(app)/sales/page-447aa2c1f51bb005.js","/_next/static/chunks/app/(app)/settings/page-acf6c1edc2a9f862.js","/_next/static/chunks/app/(app)/subscription/page-ed93ac48b31bfef7.js","/_next/static/chunks/app/(app)/supplier-records/page-c45f8194639c1b52.js","/_next/static/chunks/app/(app)/users/detail/page-aa9d067eaf5c2c5e.js","/_next/static/chunks/app/(app)/users/page-3666c45934b3e9db.js","/_next/static/chunks/app/(app)/web-orders/page-b7111a789410bfbd.js","/_next/static/chunks/app/(app)/website/page-a5033cb66cffedc7.js","/_next/static/chunks/app/(marketing)/compare/[slug]/page-b3e27857ae6cbc08.js","/_next/static/chunks/app/(marketing)/en/compare/[slug]/page-7ff4cc36309c2133.js","/_next/static/chunks/app/(marketing)/en/guides/[slug]/page-f33bd8565ca51d2b.js","/_next/static/chunks/app/(marketing)/en/guides/page-97e17257cf3ac6bf.js","/_next/static/chunks/app/(marketing)/en/layout-442470b494c945b2.js","/_next/static/chunks/app/(marketing)/en/page-55bfac2f9702c7a4.js","/_next/static/chunks/app/(marketing)/en/pricing/layout-442470b494c945b2.js","/_next/static/chunks/app/(marketing)/en/pricing/page-1e69fc96e368cd94.js","/_next/static/chunks/app/(marketing)/en/product/layout-442470b494c945b2.js","/_next/static/chunks/app/(marketing)/en/product/page-2784f4aa5fb64ef9.js","/_next/static/chunks/app/(marketing)/en/register/hosting/layout-442470b494c945b2.js","/_next/static/chunks/app/(marketing)/en/register/hosting/page-fa7e513864af480a.js","/_next/static/chunks/app/(marketing)/en/register/layout-442470b494c945b2.js","/_next/static/chunks/app/(marketing)/en/register/page-be982db80964f574.js","/_next/static/chunks/app/(marketing)/en/solutions/[slug]/page-0402fe8f236c561b.js","/_next/static/chunks/app/(marketing)/en/solutions/page-4bb7a4a586789504.js","/_next/static/chunks/app/(marketing)/en/track/layout-442470b494c945b2.js","/_next/static/chunks/app/(marketing)/en/track/page-f01d929b4cc2b12a.js","/_next/static/chunks/app/(marketing)/guides/[slug]/page-0871de4caeaf7b8a.js","/_next/static/chunks/app/(marketing)/guides/page-50f61631b1f04a39.js","/_next/static/chunks/app/(marketing)/layout-442470b494c945b2.js","/_next/static/chunks/app/(marketing)/page-32ec5d9b7fe41a9a.js","/_next/static/chunks/app/(marketing)/pricing/layout-442470b494c945b2.js","/_next/static/chunks/app/(marketing)/pricing/page-37142a8c274b02a7.js","/_next/static/chunks/app/(marketing)/product/layout-442470b494c945b2.js","/_next/static/chunks/app/(marketing)/product/page-915142de28646d2e.js","/_next/static/chunks/app/(marketing)/register/hosting/layout-442470b494c945b2.js","/_next/static/chunks/app/(marketing)/register/hosting/page-2b45853673e5dedd.js","/_next/static/chunks/app/(marketing)/register/layout-442470b494c945b2.js","/_next/static/chunks/app/(marketing)/register/page-d699de71b870ea1d.js","/_next/static/chunks/app/(marketing)/solutions/[slug]/page-ccaeeb19c3aedc9d.js","/_next/static/chunks/app/(marketing)/solutions/page-a8cfc7510c498752.js","/_next/static/chunks/app/(marketing)/track/layout-442470b494c945b2.js","/_next/static/chunks/app/(marketing)/track/page-43fb4b9a30b4c7c3.js","/_next/static/chunks/app/_not-found/page-fb60ccb3ed4b5a30.js","/_next/static/chunks/app/activate-owner/layout-442470b494c945b2.js","/_next/static/chunks/app/activate-owner/page-28eed3de06e4880d.js","/_next/static/chunks/app/forgot-password/layout-442470b494c945b2.js","/_next/static/chunks/app/forgot-password/page-be2ffb847ea0c513.js","/_next/static/chunks/app/layout-2a1642bed58ce4c1.js","/_next/static/chunks/app/login/layout-442470b494c945b2.js","/_next/static/chunks/app/login/page-964e25a768cc0b8e.js","/_next/static/chunks/app/reset-password/layout-442470b494c945b2.js","/_next/static/chunks/app/reset-password/page-335980153cf73c8c.js","/_next/static/chunks/app/robots.txt/route-442470b494c945b2.js","/_next/static/chunks/app/sitemap.xml/route-442470b494c945b2.js","/_next/static/chunks/framework-4374eae96780d8a1.js","/_next/static/chunks/main-app-282bc9487decc98d.js","/_next/static/chunks/main-bad072af1eaab979.js","/_next/static/chunks/pages/_app-4b3fb5e477a0267f.js","/_next/static/chunks/pages/_error-c970d8b55ace1b48.js","/_next/static/chunks/polyfills-42372ed130431b0a.js","/_next/static/chunks/webpack-129c927e9bd67c4f.js","/_next/static/css/f16181c489abadc4.css","/_next/static/media/011e180705008d6f-s.woff2","/_next/static/media/19cfc7226ec3afaa-s.woff2","/_next/static/media/1ebb550cd0a67fc6-s.p.woff2","/_next/static/media/21350d82a1f187e9-s.woff2","/_next/static/media/3dc379dc9b5dec12-s.p.woff2","/_next/static/media/58c726479f69cacd-s.woff2","/_next/static/media/58f386aa6b1a2a92-s.woff2","/_next/static/media/63a79a6cf340c5d2-s.p.woff2","/_next/static/media/7ba5fb2a8c88521c-s.woff2","/_next/static/media/8e9860b6e62d6359-s.woff2","/_next/static/media/92eeb95d069020cc-s.woff2","/_next/static/media/98e207f02528a563-s.p.woff2","/_next/static/media/99dcf268bda04fe5-s.woff2","/_next/static/media/ba9851c3c22cd980-s.woff2","/_next/static/media/bd9c8c62ffadd9dd-s.p.woff2","/_next/static/media/c5f10e9e72d35c52-s.woff2","/_next/static/media/c5fe6dc8356a8c31-s.woff2","/_next/static/media/cc8b755e9c1ba115-s.woff2","/_next/static/media/ce401babc0566bc1-s.woff2","/_next/static/media/d29838c109ef09b4-s.woff2","/_next/static/media/d3ebbfd689654d3a-s.p.woff2","/_next/static/media/dd994fbf464986f0-s.p.woff2","/_next/static/media/df0a9ae256c0569c-s.woff2","/_next/static/media/e40af3453d7c920a-s.woff2","/_next/static/media/e4af272ccee01ff0-s.p.woff2","/_next/static/media/e97026df054cf2a3-s.woff2","/_next/static/media/ef4d5661765d0e49-s.woff2","/_next/static/media/f15f45d13243c643-s.woff2","/_next/static/media/f952393b67d608ec-s.p.woff2","/_next/static/nrWoN064v2UiEfXMu3A2C/_buildManifest.js","/_next/static/nrWoN064v2UiEfXMu3A2C/_ssgManifest.js","/icons/apple-touch-icon.png","/icons/badge-96.png","/icons/icon-192.png","/icons/icon-512.png","/icons/icon-maskable-192.png","/icons/icon-maskable-512.png","/manifest.webmanifest"];
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
