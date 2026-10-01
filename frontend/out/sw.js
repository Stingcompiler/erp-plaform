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
const BUILD = "c3mFpNHhmiV1VCMHj7w9Y";
const CACHE = `vezano-shell-${BUILD}`;
// Every screen of the app, so the person lands on the page they asked for
// with no network — never on a different one. Filled in at build time from
// the export; the list below is the floor the PWA manifest relies on.
const PRECACHE_PAGES = ["/", "/login/", "/dashboard/", "/sales/", "/inventory/", "/returns/"];
const PRECACHE_APP_PAGES = ["/activate-owner/","/crm/","/customer-records/","/dashboard/","/debts/","/finance/","/forgot-password/","/hr/","/inventory/","/labels/","/login/","/logs/","/org/","/platform-activity/","/platform-analytics/","/platform-companies/","/platform-errors/","/platform-finance/","/platform-leads/","/platform-plans/","/platform-registrations/","/platform-seo/","/platform-subscriptions/","/platform-team/","/platform-team/member/","/platform/","/purchasing/","/reports/","/reset-password/","/returns/","/sales/","/settings/","/subscription/","/supplier-records/","/track/","/users/","/users/detail/","/web-orders/","/website/"];
// Every hashed chunk, stylesheet and font of this build, plus the manifest
// and icons — filled in at build time from the export.
const PRECACHE_ASSETS = ["/_next/static/c3mFpNHhmiV1VCMHj7w9Y/_buildManifest.js","/_next/static/c3mFpNHhmiV1VCMHj7w9Y/_ssgManifest.js","/_next/static/chunks/1052-98e5140521faae52.js","/_next/static/chunks/1139-9c2898bdfd9cfa41.js","/_next/static/chunks/1228-5dff63c581a7eb54.js","/_next/static/chunks/1255-f456c2191ed027a9.js","/_next/static/chunks/1268-0264e778c6695ff2.js","/_next/static/chunks/1492-737827e0290754df.js","/_next/static/chunks/1597-a870dc59fb0fb538.js","/_next/static/chunks/1922-557c7f1fdb42754d.js","/_next/static/chunks/1947-f3e38c475f70ec5e.js","/_next/static/chunks/222-8b9a341d0f829375.js","/_next/static/chunks/2262-622d36d512aacf00.js","/_next/static/chunks/2313-7d55580aabc1388f.js","/_next/static/chunks/2391.d0eed6031ed46fa3.js","/_next/static/chunks/2738-61e12989dc7f7dc6.js","/_next/static/chunks/280-43d2951a75ccb567.js","/_next/static/chunks/2951-4692c424d0610003.js","/_next/static/chunks/3098-a9682f52e91c87c3.js","/_next/static/chunks/3302-ce8798291078326a.js","/_next/static/chunks/3388-f3819ab090331ebc.js","/_next/static/chunks/3607-43556cae6cad733f.js","/_next/static/chunks/4103-49d3206b832df75f.js","/_next/static/chunks/4121-1720a2df2a223bf3.js","/_next/static/chunks/4545-f516c64e572ac8dd.js","/_next/static/chunks/4796-ddc6021c16d1db57.js","/_next/static/chunks/4825-39361b1a36a41e53.js","/_next/static/chunks/4939-749f032e96a7dc89.js","/_next/static/chunks/4bd1b696-100b9d70ed4e49c1.js","/_next/static/chunks/5263-f11b7300593a4ad1.js","/_next/static/chunks/5421.d04d2b84e94672b6.js","/_next/static/chunks/6208-3ced53fba7eff49a.js","/_next/static/chunks/6486-19ddc23ba59b7299.js","/_next/static/chunks/6565-5152f1e622d17e4b.js","/_next/static/chunks/7152-d18fa47176f53fca.js","/_next/static/chunks/7289-ce2dea732489a2b2.js","/_next/static/chunks/7403-f9cefcab9d32067a.js","/_next/static/chunks/8109.46238d46d534e00a.js","/_next/static/chunks/8130-ab940df9cf6f8246.js","/_next/static/chunks/8703-d0b6fc5589fca124.js","/_next/static/chunks/9053-0878f3d81211696d.js","/_next/static/chunks/9285-502e51eb8173e9df.js","/_next/static/chunks/9989-af33a7ccc22a1e77.js","/_next/static/chunks/app/(app)/crm/page-995a2e053bec65c6.js","/_next/static/chunks/app/(app)/customer-records/page-f9436f56012f1b2c.js","/_next/static/chunks/app/(app)/dashboard/page-6ccb492befc78d23.js","/_next/static/chunks/app/(app)/debts/page-7c4d6683435ff077.js","/_next/static/chunks/app/(app)/finance/page-ce40afae0de1efab.js","/_next/static/chunks/app/(app)/hr/page-e87b5ffbb0593e60.js","/_next/static/chunks/app/(app)/inventory/page-9dc2c0db4ceceefc.js","/_next/static/chunks/app/(app)/labels/page-4e85aa436eca0222.js","/_next/static/chunks/app/(app)/layout-3a50751da85c8f15.js","/_next/static/chunks/app/(app)/logs/page-a5c4f1a09a4c52bc.js","/_next/static/chunks/app/(app)/org/page-b393c3e0af7efa80.js","/_next/static/chunks/app/(app)/platform-activity/page-d757c41729030869.js","/_next/static/chunks/app/(app)/platform-analytics/page-e27a04b7c8d19e95.js","/_next/static/chunks/app/(app)/platform-companies/page-ebf944beb8e7a26b.js","/_next/static/chunks/app/(app)/platform-errors/page-13db3a5424311759.js","/_next/static/chunks/app/(app)/platform-finance/page-be9bcee21f73a5d7.js","/_next/static/chunks/app/(app)/platform-leads/page-967398c0e905fb16.js","/_next/static/chunks/app/(app)/platform-plans/page-805212ad2d2f56f8.js","/_next/static/chunks/app/(app)/platform-registrations/page-ad4ccbae2572bc25.js","/_next/static/chunks/app/(app)/platform-seo/page-0c630ee38634970d.js","/_next/static/chunks/app/(app)/platform-subscriptions/page-6a6091323472fd9e.js","/_next/static/chunks/app/(app)/platform-team/member/page-b33b7e49dacf4281.js","/_next/static/chunks/app/(app)/platform-team/page-67daae4b3ff9b617.js","/_next/static/chunks/app/(app)/platform/page-6a174dbc5401c12f.js","/_next/static/chunks/app/(app)/purchasing/page-ed32283b9adb4102.js","/_next/static/chunks/app/(app)/reports/page-b1723f3bd09c5f5a.js","/_next/static/chunks/app/(app)/returns/page-a81f31fe6194f75c.js","/_next/static/chunks/app/(app)/sales/page-3a542fd173e9b4cb.js","/_next/static/chunks/app/(app)/settings/page-f552794f2d2ede6a.js","/_next/static/chunks/app/(app)/subscription/page-569f170ba00ca2b5.js","/_next/static/chunks/app/(app)/supplier-records/page-7ee50e3e8e8d8f6d.js","/_next/static/chunks/app/(app)/users/detail/page-a4e87e020ecbc15d.js","/_next/static/chunks/app/(app)/users/page-8028c17b29c2287e.js","/_next/static/chunks/app/(app)/web-orders/page-afbd11cf3ead7035.js","/_next/static/chunks/app/(app)/website/page-265f86df29e3d1c8.js","/_next/static/chunks/app/(marketing)/compare/[slug]/page-9bc9de7aea42a0cb.js","/_next/static/chunks/app/(marketing)/en/compare/[slug]/page-c8c7c267f075c31f.js","/_next/static/chunks/app/(marketing)/en/guides/[slug]/page-30db5176f577e211.js","/_next/static/chunks/app/(marketing)/en/guides/page-6cf48f01487ae3fb.js","/_next/static/chunks/app/(marketing)/en/layout-d306913d2552031f.js","/_next/static/chunks/app/(marketing)/en/page-b652208b83344584.js","/_next/static/chunks/app/(marketing)/en/pricing/layout-d306913d2552031f.js","/_next/static/chunks/app/(marketing)/en/pricing/page-f1f851763132bf37.js","/_next/static/chunks/app/(marketing)/en/product/layout-d306913d2552031f.js","/_next/static/chunks/app/(marketing)/en/product/page-c6d8891a00cf2f8b.js","/_next/static/chunks/app/(marketing)/en/register/hosting/layout-d306913d2552031f.js","/_next/static/chunks/app/(marketing)/en/register/hosting/page-53360dd77e8a24c5.js","/_next/static/chunks/app/(marketing)/en/register/layout-d306913d2552031f.js","/_next/static/chunks/app/(marketing)/en/register/page-2f4aa2a85c0fcfc4.js","/_next/static/chunks/app/(marketing)/en/solutions/[slug]/page-c3ca9503065fd5c0.js","/_next/static/chunks/app/(marketing)/en/solutions/page-5ff91f5a828c716f.js","/_next/static/chunks/app/(marketing)/en/track/layout-d306913d2552031f.js","/_next/static/chunks/app/(marketing)/en/track/page-c77752843c6c5cc5.js","/_next/static/chunks/app/(marketing)/guides/[slug]/page-f717b3783c6643ea.js","/_next/static/chunks/app/(marketing)/guides/page-c240436044d94647.js","/_next/static/chunks/app/(marketing)/layout-528c9a6099246d36.js","/_next/static/chunks/app/(marketing)/page-19003eeb9ae5bc3f.js","/_next/static/chunks/app/(marketing)/pricing/layout-d306913d2552031f.js","/_next/static/chunks/app/(marketing)/pricing/page-5b253a5ec7a768e8.js","/_next/static/chunks/app/(marketing)/product/layout-d306913d2552031f.js","/_next/static/chunks/app/(marketing)/product/page-290679b2c4e52f3e.js","/_next/static/chunks/app/(marketing)/register/hosting/layout-d306913d2552031f.js","/_next/static/chunks/app/(marketing)/register/hosting/page-596f91956b57a1e2.js","/_next/static/chunks/app/(marketing)/register/layout-d306913d2552031f.js","/_next/static/chunks/app/(marketing)/register/page-ad39e3242a024484.js","/_next/static/chunks/app/(marketing)/solutions/[slug]/page-3d198d16a93fa9e9.js","/_next/static/chunks/app/(marketing)/solutions/page-b9e5f66af10169cb.js","/_next/static/chunks/app/(marketing)/track/layout-d306913d2552031f.js","/_next/static/chunks/app/(marketing)/track/page-ada22386101814b6.js","/_next/static/chunks/app/_not-found/page-fb60ccb3ed4b5a30.js","/_next/static/chunks/app/activate-owner/layout-3687c6ac066c4cbd.js","/_next/static/chunks/app/activate-owner/page-be54555c68fa32b4.js","/_next/static/chunks/app/forgot-password/layout-3687c6ac066c4cbd.js","/_next/static/chunks/app/forgot-password/page-09f897750cabeb38.js","/_next/static/chunks/app/layout-57c9f489969ae2f9.js","/_next/static/chunks/app/login/layout-3687c6ac066c4cbd.js","/_next/static/chunks/app/login/page-f0e18426049f5440.js","/_next/static/chunks/app/reset-password/layout-3687c6ac066c4cbd.js","/_next/static/chunks/app/reset-password/page-036a0ed753f2bf4b.js","/_next/static/chunks/app/robots.txt/route-d306913d2552031f.js","/_next/static/chunks/app/sitemap.xml/route-d306913d2552031f.js","/_next/static/chunks/framework-4374eae96780d8a1.js","/_next/static/chunks/main-app-282bc9487decc98d.js","/_next/static/chunks/main-bad072af1eaab979.js","/_next/static/chunks/pages/_app-4b3fb5e477a0267f.js","/_next/static/chunks/pages/_error-c970d8b55ace1b48.js","/_next/static/chunks/polyfills-42372ed130431b0a.js","/_next/static/chunks/webpack-9b198841c3d98948.js","/_next/static/css/77fdca18a18c7e83.css","/_next/static/css/8a5a4fa230ce7eed.css","/_next/static/media/011e180705008d6f.woff2","/_next/static/media/19cfc7226ec3afaa.woff2","/_next/static/media/1ebb550cd0a67fc6.p.woff2","/_next/static/media/21350d82a1f187e9.woff2","/_next/static/media/3dc379dc9b5dec12.p.woff2","/_next/static/media/58c726479f69cacd.woff2","/_next/static/media/58f386aa6b1a2a92.woff2","/_next/static/media/63a79a6cf340c5d2.p.woff2","/_next/static/media/7ba5fb2a8c88521c.woff2","/_next/static/media/8e9860b6e62d6359.woff2","/_next/static/media/92eeb95d069020cc.woff2","/_next/static/media/98e207f02528a563.p.woff2","/_next/static/media/99dcf268bda04fe5.woff2","/_next/static/media/ba9851c3c22cd980.woff2","/_next/static/media/bd9c8c62ffadd9dd.p.woff2","/_next/static/media/c5f10e9e72d35c52.woff2","/_next/static/media/c5fe6dc8356a8c31.woff2","/_next/static/media/cc8b755e9c1ba115.woff2","/_next/static/media/ce401babc0566bc1.woff2","/_next/static/media/d29838c109ef09b4.woff2","/_next/static/media/d3ebbfd689654d3a.p.woff2","/_next/static/media/dd994fbf464986f0.p.woff2","/_next/static/media/df0a9ae256c0569c.woff2","/_next/static/media/e40af3453d7c920a.woff2","/_next/static/media/e4af272ccee01ff0.p.woff2","/_next/static/media/e97026df054cf2a3.woff2","/_next/static/media/ef4d5661765d0e49.woff2","/_next/static/media/f15f45d13243c643.woff2","/_next/static/media/f952393b67d608ec.p.woff2","/icons/apple-touch-icon.png","/icons/badge-96.png","/icons/icon-192.png","/icons/icon-512.png","/icons/icon-maskable-192.png","/icons/icon-maskable-512.png","/manifest.webmanifest"];
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
