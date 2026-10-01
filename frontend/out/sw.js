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
const BUILD = "5B30oizMcTeQvEK2kZXoO";
const CACHE = `vezano-shell-${BUILD}`;
// Every screen of the app, so the person lands on the page they asked for
// with no network — never on a different one. Filled in at build time from
// the export; the list below is the floor the PWA manifest relies on.
const PRECACHE_PAGES = ["/", "/login/", "/dashboard/", "/sales/", "/inventory/", "/returns/"];
const PRECACHE_APP_PAGES = ["/activate-owner/","/crm/","/customer-records/","/dashboard/","/debts/","/finance/","/forgot-password/","/hr/","/inventory/","/labels/","/login/","/logs/","/org/","/platform-activity/","/platform-analytics/","/platform-companies/","/platform-errors/","/platform-finance/","/platform-leads/","/platform-plans/","/platform-registrations/","/platform-seo/","/platform-subscriptions/","/platform-team/","/platform-team/member/","/platform/","/purchasing/","/reports/","/reset-password/","/returns/","/sales/","/settings/","/subscription/","/supplier-records/","/track/","/users/","/users/detail/","/web-orders/","/website/"];
// Every hashed chunk, stylesheet and font of this build, plus the manifest
// and icons — filled in at build time from the export.
const PRECACHE_ASSETS = ["/_next/static/5B30oizMcTeQvEK2kZXoO/_buildManifest.js","/_next/static/5B30oizMcTeQvEK2kZXoO/_ssgManifest.js","/_next/static/chunks/1328-53adf64957863e53.js","/_next/static/chunks/1391-0b93ee9d9f7c21e5.js","/_next/static/chunks/1409-b3ce6e6affad694c.js","/_next/static/chunks/1698-66865647035d1996.js","/_next/static/chunks/182-f26e88b724bd5e6e.js","/_next/static/chunks/2126-608b0a9051caf73e.js","/_next/static/chunks/2785-31913625a873f56c.js","/_next/static/chunks/3117-61a68afb919b8d59.js","/_next/static/chunks/3233-40e2a6e2a5c7ed47.js","/_next/static/chunks/3360-251cb8182434c64c.js","/_next/static/chunks/3415-daabf772037de0d5.js","/_next/static/chunks/3995-193cf33b08e91925.js","/_next/static/chunks/4023-49cdbe58402e1f5f.js","/_next/static/chunks/40b91c18-03576e02c01e0947.js","/_next/static/chunks/4265-a68bb7afb1251911.js","/_next/static/chunks/4462.0f420d4f6374ab9b.js","/_next/static/chunks/476-e56912d8c7544d56.js","/_next/static/chunks/4838-398c296d08c00313.js","/_next/static/chunks/5405.a2853eec62072dae.js","/_next/static/chunks/5410-087bc64c21c04d17.js","/_next/static/chunks/5811-c5306e37bd205f86.js","/_next/static/chunks/6702-becc1926d1626e66.js","/_next/static/chunks/689-a0465b186118c2fe.js","/_next/static/chunks/694-73d22f93c292b472.js","/_next/static/chunks/7089-af84b523904bfac2.js","/_next/static/chunks/7535-20577c64ca0d6cfa.js","/_next/static/chunks/7536-15fbefc9cc695446.js","/_next/static/chunks/7769-313f6fad97c64c58.js","/_next/static/chunks/7941-e9ce3acebb531c99.js","/_next/static/chunks/7985-048546177220fd36.js","/_next/static/chunks/8199-b7822f9e69122fc5.js","/_next/static/chunks/8288-1bb4dbcffa7aee6f.js","/_next/static/chunks/8430-f929184bb61c728a.js","/_next/static/chunks/8557.bdee3fe4b34fcf91.js","/_next/static/chunks/8690-c9c7775750cdbada.js","/_next/static/chunks/8890-93390470aa87db92.js","/_next/static/chunks/9151-1e1f4959df8c62f1.js","/_next/static/chunks/9242-5dadef187f312ae1.js","/_next/static/chunks/9535-13712210b96ba167.js","/_next/static/chunks/9681-44d718ea65c60825.js","/_next/static/chunks/9865-284dd54e354b5acb.js","/_next/static/chunks/app/(app)/crm/page-51d0dbb2083cf01b.js","/_next/static/chunks/app/(app)/customer-records/page-243078869cfcbb3c.js","/_next/static/chunks/app/(app)/dashboard/page-90c0963dc296c793.js","/_next/static/chunks/app/(app)/debts/page-61dea79870d929ed.js","/_next/static/chunks/app/(app)/finance/page-eeba25a930bd526f.js","/_next/static/chunks/app/(app)/hr/page-451eb275270aa484.js","/_next/static/chunks/app/(app)/inventory/page-26013de18b275332.js","/_next/static/chunks/app/(app)/labels/page-619501c13b49570b.js","/_next/static/chunks/app/(app)/layout-8808b00e63adba9b.js","/_next/static/chunks/app/(app)/logs/page-0e1eb6ff6cd53f96.js","/_next/static/chunks/app/(app)/org/page-b98bf78f6695d0a3.js","/_next/static/chunks/app/(app)/platform-activity/page-1acf3a231d5aa5c7.js","/_next/static/chunks/app/(app)/platform-analytics/page-1c89301196643517.js","/_next/static/chunks/app/(app)/platform-companies/page-b512d1a3c073eb80.js","/_next/static/chunks/app/(app)/platform-errors/page-f0ca847f5e0ecc02.js","/_next/static/chunks/app/(app)/platform-finance/page-c12e3f9f97cf48c1.js","/_next/static/chunks/app/(app)/platform-leads/page-5b994ed610f96531.js","/_next/static/chunks/app/(app)/platform-plans/page-c8a4352e28aafb11.js","/_next/static/chunks/app/(app)/platform-registrations/page-a72fda6336fd3d44.js","/_next/static/chunks/app/(app)/platform-seo/page-02eb200c5ccdd597.js","/_next/static/chunks/app/(app)/platform-subscriptions/page-3baaf719ccbb12ee.js","/_next/static/chunks/app/(app)/platform-team/member/page-e5c602f64ed91dc2.js","/_next/static/chunks/app/(app)/platform-team/page-c5bca3140b0d8690.js","/_next/static/chunks/app/(app)/platform/page-bfc278155d446a9c.js","/_next/static/chunks/app/(app)/purchasing/page-7fb0fbff63d90ec0.js","/_next/static/chunks/app/(app)/reports/page-fdf06766e1815bba.js","/_next/static/chunks/app/(app)/returns/page-18da62958bb4594b.js","/_next/static/chunks/app/(app)/sales/page-3d1cfeafc612be0b.js","/_next/static/chunks/app/(app)/settings/page-ea702b442e3c6729.js","/_next/static/chunks/app/(app)/subscription/page-8d516526769ccf24.js","/_next/static/chunks/app/(app)/supplier-records/page-4eb0b43f6f242795.js","/_next/static/chunks/app/(app)/users/detail/page-74dd30e866e40de6.js","/_next/static/chunks/app/(app)/users/page-1802212c5cf6b9d6.js","/_next/static/chunks/app/(app)/web-orders/page-712304c640371ed5.js","/_next/static/chunks/app/(app)/website/page-f9b5253db2e185a2.js","/_next/static/chunks/app/(marketing)/compare/[slug]/page-5300bbc402b807e5.js","/_next/static/chunks/app/(marketing)/en/compare/[slug]/page-250f976a2432e187.js","/_next/static/chunks/app/(marketing)/en/guides/[slug]/page-276d6bc40c11200d.js","/_next/static/chunks/app/(marketing)/en/guides/page-9b2564f3c65fad10.js","/_next/static/chunks/app/(marketing)/en/layout-ddaba7143b3b003d.js","/_next/static/chunks/app/(marketing)/en/page-72e06241927d71f7.js","/_next/static/chunks/app/(marketing)/en/pricing/layout-ddaba7143b3b003d.js","/_next/static/chunks/app/(marketing)/en/pricing/page-b9362f21eaa9e7cd.js","/_next/static/chunks/app/(marketing)/en/product/layout-ddaba7143b3b003d.js","/_next/static/chunks/app/(marketing)/en/product/page-1660626eb46c5d38.js","/_next/static/chunks/app/(marketing)/en/register/hosting/layout-ddaba7143b3b003d.js","/_next/static/chunks/app/(marketing)/en/register/hosting/page-4832db8566405ab0.js","/_next/static/chunks/app/(marketing)/en/register/layout-ddaba7143b3b003d.js","/_next/static/chunks/app/(marketing)/en/register/page-2fc4d8190e7389a3.js","/_next/static/chunks/app/(marketing)/en/solutions/[slug]/page-f831318bf8b67b6e.js","/_next/static/chunks/app/(marketing)/en/solutions/page-c66fec8ffc320592.js","/_next/static/chunks/app/(marketing)/en/track/layout-ddaba7143b3b003d.js","/_next/static/chunks/app/(marketing)/en/track/page-322d62e608aade55.js","/_next/static/chunks/app/(marketing)/guides/[slug]/page-18083d1ad625604f.js","/_next/static/chunks/app/(marketing)/guides/page-a3806fdabe2e0be9.js","/_next/static/chunks/app/(marketing)/layout-cce8cbf3b85f29c6.js","/_next/static/chunks/app/(marketing)/page-6bb41758882f94ac.js","/_next/static/chunks/app/(marketing)/pricing/layout-ddaba7143b3b003d.js","/_next/static/chunks/app/(marketing)/pricing/page-e9ce34d9409599a9.js","/_next/static/chunks/app/(marketing)/product/layout-ddaba7143b3b003d.js","/_next/static/chunks/app/(marketing)/product/page-a7e842eb895632ef.js","/_next/static/chunks/app/(marketing)/register/hosting/layout-ddaba7143b3b003d.js","/_next/static/chunks/app/(marketing)/register/hosting/page-4185015111c1524d.js","/_next/static/chunks/app/(marketing)/register/layout-ddaba7143b3b003d.js","/_next/static/chunks/app/(marketing)/register/page-27d4334451e5052a.js","/_next/static/chunks/app/(marketing)/solutions/[slug]/page-d24c9896afa2587e.js","/_next/static/chunks/app/(marketing)/solutions/page-21359d4c007441c6.js","/_next/static/chunks/app/(marketing)/track/layout-ddaba7143b3b003d.js","/_next/static/chunks/app/(marketing)/track/page-a4d694ba6c630b0a.js","/_next/static/chunks/app/_not-found/page-93f5ecd9b5a1b8d5.js","/_next/static/chunks/app/activate-owner/layout-47632848373e9040.js","/_next/static/chunks/app/activate-owner/page-b1966fc5501f32c4.js","/_next/static/chunks/app/forgot-password/layout-47632848373e9040.js","/_next/static/chunks/app/forgot-password/page-8c917c4339b310b5.js","/_next/static/chunks/app/layout-befdccd521253920.js","/_next/static/chunks/app/login/layout-47632848373e9040.js","/_next/static/chunks/app/login/page-fddbc92202133972.js","/_next/static/chunks/app/reset-password/layout-47632848373e9040.js","/_next/static/chunks/app/reset-password/page-dc3950373dd3193f.js","/_next/static/chunks/app/robots.txt/route-ddaba7143b3b003d.js","/_next/static/chunks/app/sitemap.xml/route-ddaba7143b3b003d.js","/_next/static/chunks/framework-ac871cde7d705c3a.js","/_next/static/chunks/main-61969269e7b3dad5.js","/_next/static/chunks/main-app-d3c2614b980cfab3.js","/_next/static/chunks/pages/_app-c0e3f7ff6ef43cb0.js","/_next/static/chunks/pages/_error-6bf3d2bf6fe2d033.js","/_next/static/chunks/polyfills-42372ed130431b0a.js","/_next/static/chunks/webpack-76fb0d753073358b.js","/_next/static/css/ba3584122835bec0.css","/_next/static/media/011e180705008d6f.woff2","/_next/static/media/19cfc7226ec3afaa.woff2","/_next/static/media/1ebb550cd0a67fc6.p.woff2","/_next/static/media/21350d82a1f187e9.woff2","/_next/static/media/3dc379dc9b5dec12.p.woff2","/_next/static/media/58c726479f69cacd.woff2","/_next/static/media/58f386aa6b1a2a92.woff2","/_next/static/media/63a79a6cf340c5d2.p.woff2","/_next/static/media/7ba5fb2a8c88521c.woff2","/_next/static/media/8e9860b6e62d6359.woff2","/_next/static/media/92eeb95d069020cc.woff2","/_next/static/media/98e207f02528a563.p.woff2","/_next/static/media/99dcf268bda04fe5.woff2","/_next/static/media/ba9851c3c22cd980.woff2","/_next/static/media/bd9c8c62ffadd9dd.p.woff2","/_next/static/media/c5f10e9e72d35c52.woff2","/_next/static/media/c5fe6dc8356a8c31.woff2","/_next/static/media/cc8b755e9c1ba115.woff2","/_next/static/media/ce401babc0566bc1.woff2","/_next/static/media/d29838c109ef09b4.woff2","/_next/static/media/d3ebbfd689654d3a.p.woff2","/_next/static/media/dd994fbf464986f0.p.woff2","/_next/static/media/df0a9ae256c0569c.woff2","/_next/static/media/e40af3453d7c920a.woff2","/_next/static/media/e4af272ccee01ff0.p.woff2","/_next/static/media/e97026df054cf2a3.woff2","/_next/static/media/ef4d5661765d0e49.woff2","/_next/static/media/f15f45d13243c643.woff2","/_next/static/media/f952393b67d608ec.p.woff2","/icons/apple-touch-icon.png","/icons/badge-96.png","/icons/icon-192.png","/icons/icon-512.png","/icons/icon-maskable-192.png","/icons/icon-maskable-512.png","/manifest.webmanifest"];
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
