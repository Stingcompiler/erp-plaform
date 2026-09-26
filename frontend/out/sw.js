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
const BUILD = "Dtdzyy4Ms-dFS8Vv4Ay1q";
const CACHE = `vezano-shell-${BUILD}`;
// Every screen of the app, so the person lands on the page they asked for
// with no network — never on a different one. Filled in at build time from
// the export; the list below is the floor the PWA manifest relies on.
const PRECACHE_PAGES = ["/", "/login/", "/dashboard/", "/sales/", "/inventory/", "/returns/"];
const PRECACHE_APP_PAGES = ["/activate-owner/","/crm/","/customer-records/","/dashboard/","/debts/","/finance/","/forgot-password/","/hr/","/inventory/","/labels/","/login/","/logs/","/org/","/platform-activity/","/platform-analytics/","/platform-companies/","/platform-errors/","/platform-finance/","/platform-leads/","/platform-plans/","/platform-registrations/","/platform-seo/","/platform-subscriptions/","/platform-team/","/platform-team/member/","/platform/","/purchasing/","/reports/","/reset-password/","/returns/","/sales/","/settings/","/subscription/","/supplier-records/","/track/","/users/","/users/detail/","/web-orders/","/website/"];
// Every hashed chunk, stylesheet and font of this build, plus the manifest
// and icons — filled in at build time from the export.
const PRECACHE_ASSETS = ["/_next/static/Dtdzyy4Ms-dFS8Vv4Ay1q/_buildManifest.js","/_next/static/Dtdzyy4Ms-dFS8Vv4Ay1q/_ssgManifest.js","/_next/static/chunks/1228-5dff63c581a7eb54.js","/_next/static/chunks/1255-f456c2191ed027a9.js","/_next/static/chunks/1268-f6d3f4205ba01aa5.js","/_next/static/chunks/1360-fa52c5ac753b049b.js","/_next/static/chunks/1597-571d6d678f664d18.js","/_next/static/chunks/1947-70a7da8650dadda0.js","/_next/static/chunks/2238-83611a76e7316e86.js","/_next/static/chunks/280-43d2951a75ccb567.js","/_next/static/chunks/3098-90f1dfd0d7bf3437.js","/_next/static/chunks/3302-e4346b3908b16773.js","/_next/static/chunks/3607-37f12abfdbd6bc6e.js","/_next/static/chunks/3830-3f12a7b04facf322.js","/_next/static/chunks/3920-a36e8a49deddcadc.js","/_next/static/chunks/4050-ef68162411863d0b.js","/_next/static/chunks/4059-537091c40bc36e38.js","/_next/static/chunks/4796-ddc6021c16d1db57.js","/_next/static/chunks/4bd1b696-100b9d70ed4e49c1.js","/_next/static/chunks/5053-67060226aac00eb2.js","/_next/static/chunks/5421.d04d2b84e94672b6.js","/_next/static/chunks/5719-a76800149790aa88.js","/_next/static/chunks/6105-416b4befcdf92d23.js","/_next/static/chunks/6394-5458bf7dc51ffe42.js","/_next/static/chunks/6693-0048341addb4f136.js","/_next/static/chunks/7032-980dd4e2b22081c3.js","/_next/static/chunks/7289-ce2dea732489a2b2.js","/_next/static/chunks/7423-9b196178f35afd07.js","/_next/static/chunks/7731-730b1a698d982393.js","/_next/static/chunks/7865-52eda843c908da3b.js","/_next/static/chunks/8698-259a5aca85ce26ad.js","/_next/static/chunks/8838-0764cda4a58c0fa6.js","/_next/static/chunks/9285-020255ac0de1898c.js","/_next/static/chunks/9989-d8537ffacc6bf84b.js","/_next/static/chunks/app/(app)/crm/page-7ea47f4351eae05e.js","/_next/static/chunks/app/(app)/customer-records/page-375da91eb3699c8e.js","/_next/static/chunks/app/(app)/dashboard/page-3f353bfeb16139f5.js","/_next/static/chunks/app/(app)/debts/page-db8d508fde18c89f.js","/_next/static/chunks/app/(app)/finance/page-c3a7a1b990e38d8d.js","/_next/static/chunks/app/(app)/hr/page-95090c8d4205dde1.js","/_next/static/chunks/app/(app)/inventory/page-fa087d9b6f98a321.js","/_next/static/chunks/app/(app)/labels/page-935ab1cf434e3ff1.js","/_next/static/chunks/app/(app)/layout-6cf19d18afcabb50.js","/_next/static/chunks/app/(app)/logs/page-0b275e213295d5d3.js","/_next/static/chunks/app/(app)/org/page-391e384032821d8f.js","/_next/static/chunks/app/(app)/platform-activity/page-d3466367fe2073b5.js","/_next/static/chunks/app/(app)/platform-analytics/page-a40b75e3ef1d5723.js","/_next/static/chunks/app/(app)/platform-companies/page-5fc2aabe12eedde5.js","/_next/static/chunks/app/(app)/platform-errors/page-360fc6903ae6e603.js","/_next/static/chunks/app/(app)/platform-finance/page-547e226bd4d070a2.js","/_next/static/chunks/app/(app)/platform-leads/page-b3a41f2b4eaf7420.js","/_next/static/chunks/app/(app)/platform-plans/page-bd144dede98d8d5e.js","/_next/static/chunks/app/(app)/platform-registrations/page-98e0f30401d734f9.js","/_next/static/chunks/app/(app)/platform-seo/page-1d7acb1243921377.js","/_next/static/chunks/app/(app)/platform-subscriptions/page-7123a95fdaa32d1b.js","/_next/static/chunks/app/(app)/platform-team/member/page-6cc0045fbca5059d.js","/_next/static/chunks/app/(app)/platform-team/page-b9f20bf9a3d1c6a5.js","/_next/static/chunks/app/(app)/platform/page-8e95977e04a7832b.js","/_next/static/chunks/app/(app)/purchasing/page-2c1124bc0918664f.js","/_next/static/chunks/app/(app)/reports/page-001414b9f1ecf8dc.js","/_next/static/chunks/app/(app)/returns/page-5d58515a876e7dec.js","/_next/static/chunks/app/(app)/sales/page-dc8ed5b8eeb8407e.js","/_next/static/chunks/app/(app)/settings/page-2e1a32ec8430f28f.js","/_next/static/chunks/app/(app)/subscription/page-3c522e4f744d7343.js","/_next/static/chunks/app/(app)/supplier-records/page-73e4f43b3e1ebcd2.js","/_next/static/chunks/app/(app)/users/detail/page-0cc8a61e91987eb1.js","/_next/static/chunks/app/(app)/users/page-7bf55b897ec55688.js","/_next/static/chunks/app/(app)/web-orders/page-a746a3c65af9b3b1.js","/_next/static/chunks/app/(app)/website/page-b5a999065e58471c.js","/_next/static/chunks/app/(marketing)/compare/[slug]/page-34dc054800d8a30d.js","/_next/static/chunks/app/(marketing)/en/compare/[slug]/page-9fa55b8ca7225267.js","/_next/static/chunks/app/(marketing)/en/guides/[slug]/page-ddf3b2793ab2d3d2.js","/_next/static/chunks/app/(marketing)/en/guides/page-0d3bd3545be59daf.js","/_next/static/chunks/app/(marketing)/en/layout-442470b494c945b2.js","/_next/static/chunks/app/(marketing)/en/page-ea4e2cdd1b64d667.js","/_next/static/chunks/app/(marketing)/en/pricing/layout-442470b494c945b2.js","/_next/static/chunks/app/(marketing)/en/pricing/page-7107e153ddcff801.js","/_next/static/chunks/app/(marketing)/en/product/layout-442470b494c945b2.js","/_next/static/chunks/app/(marketing)/en/product/page-2784f4aa5fb64ef9.js","/_next/static/chunks/app/(marketing)/en/register/hosting/layout-442470b494c945b2.js","/_next/static/chunks/app/(marketing)/en/register/hosting/page-fa7e513864af480a.js","/_next/static/chunks/app/(marketing)/en/register/layout-442470b494c945b2.js","/_next/static/chunks/app/(marketing)/en/register/page-8470d6d6c08e263f.js","/_next/static/chunks/app/(marketing)/en/solutions/[slug]/page-e8f2a88adff1c236.js","/_next/static/chunks/app/(marketing)/en/solutions/page-07653a78856c99d5.js","/_next/static/chunks/app/(marketing)/en/track/layout-442470b494c945b2.js","/_next/static/chunks/app/(marketing)/en/track/page-f01d929b4cc2b12a.js","/_next/static/chunks/app/(marketing)/guides/[slug]/page-143a67046520011a.js","/_next/static/chunks/app/(marketing)/guides/page-7daf459fb340567b.js","/_next/static/chunks/app/(marketing)/layout-442470b494c945b2.js","/_next/static/chunks/app/(marketing)/page-beeb88ab0133fe57.js","/_next/static/chunks/app/(marketing)/pricing/layout-442470b494c945b2.js","/_next/static/chunks/app/(marketing)/pricing/page-883084e6884a7dd5.js","/_next/static/chunks/app/(marketing)/product/layout-442470b494c945b2.js","/_next/static/chunks/app/(marketing)/product/page-915142de28646d2e.js","/_next/static/chunks/app/(marketing)/register/hosting/layout-442470b494c945b2.js","/_next/static/chunks/app/(marketing)/register/hosting/page-2b45853673e5dedd.js","/_next/static/chunks/app/(marketing)/register/layout-442470b494c945b2.js","/_next/static/chunks/app/(marketing)/register/page-f29f6b81cd187631.js","/_next/static/chunks/app/(marketing)/solutions/[slug]/page-3a0a346f17e3bd7a.js","/_next/static/chunks/app/(marketing)/solutions/page-f7bdb11f1387a136.js","/_next/static/chunks/app/(marketing)/track/layout-442470b494c945b2.js","/_next/static/chunks/app/(marketing)/track/page-43fb4b9a30b4c7c3.js","/_next/static/chunks/app/_not-found/page-fb60ccb3ed4b5a30.js","/_next/static/chunks/app/activate-owner/layout-442470b494c945b2.js","/_next/static/chunks/app/activate-owner/page-9efbcd068a16acaa.js","/_next/static/chunks/app/forgot-password/layout-442470b494c945b2.js","/_next/static/chunks/app/forgot-password/page-bd50b5efce8a15e8.js","/_next/static/chunks/app/layout-8de5d1ccf156636a.js","/_next/static/chunks/app/login/layout-442470b494c945b2.js","/_next/static/chunks/app/login/page-69451c42355e0384.js","/_next/static/chunks/app/reset-password/layout-442470b494c945b2.js","/_next/static/chunks/app/reset-password/page-6a29dfdc6e4c9ea2.js","/_next/static/chunks/app/robots.txt/route-442470b494c945b2.js","/_next/static/chunks/app/sitemap.xml/route-442470b494c945b2.js","/_next/static/chunks/framework-4374eae96780d8a1.js","/_next/static/chunks/main-app-282bc9487decc98d.js","/_next/static/chunks/main-bad072af1eaab979.js","/_next/static/chunks/pages/_app-4b3fb5e477a0267f.js","/_next/static/chunks/pages/_error-c970d8b55ace1b48.js","/_next/static/chunks/polyfills-42372ed130431b0a.js","/_next/static/chunks/webpack-76f6cdf0dc654ec9.js","/_next/static/css/99c91d76b864f12a.css","/_next/static/media/011e180705008d6f-s.woff2","/_next/static/media/19cfc7226ec3afaa-s.woff2","/_next/static/media/1ebb550cd0a67fc6-s.p.woff2","/_next/static/media/21350d82a1f187e9-s.woff2","/_next/static/media/3dc379dc9b5dec12-s.p.woff2","/_next/static/media/58c726479f69cacd-s.woff2","/_next/static/media/58f386aa6b1a2a92-s.woff2","/_next/static/media/63a79a6cf340c5d2-s.p.woff2","/_next/static/media/7ba5fb2a8c88521c-s.woff2","/_next/static/media/8e9860b6e62d6359-s.woff2","/_next/static/media/92eeb95d069020cc-s.woff2","/_next/static/media/98e207f02528a563-s.p.woff2","/_next/static/media/99dcf268bda04fe5-s.woff2","/_next/static/media/ba9851c3c22cd980-s.woff2","/_next/static/media/bd9c8c62ffadd9dd-s.p.woff2","/_next/static/media/c5f10e9e72d35c52-s.woff2","/_next/static/media/c5fe6dc8356a8c31-s.woff2","/_next/static/media/cc8b755e9c1ba115-s.woff2","/_next/static/media/ce401babc0566bc1-s.woff2","/_next/static/media/d29838c109ef09b4-s.woff2","/_next/static/media/d3ebbfd689654d3a-s.p.woff2","/_next/static/media/dd994fbf464986f0-s.p.woff2","/_next/static/media/df0a9ae256c0569c-s.woff2","/_next/static/media/e40af3453d7c920a-s.woff2","/_next/static/media/e4af272ccee01ff0-s.p.woff2","/_next/static/media/e97026df054cf2a3-s.woff2","/_next/static/media/ef4d5661765d0e49-s.woff2","/_next/static/media/f15f45d13243c643-s.woff2","/_next/static/media/f952393b67d608ec-s.p.woff2","/icons/apple-touch-icon.png","/icons/badge-96.png","/icons/icon-192.png","/icons/icon-512.png","/icons/icon-maskable-192.png","/icons/icon-maskable-512.png","/manifest.webmanifest"];
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
