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
const BUILD = "rOEh1Iuh__VTlRhyFwYvK";
const CACHE = `vezano-shell-${BUILD}`;
// Every screen of the app, so the person lands on the page they asked for
// with no network — never on a different one. Filled in at build time from
// the export; the list below is the floor the PWA manifest relies on.
const PRECACHE_PAGES = ["/", "/login/", "/dashboard/", "/sales/", "/inventory/", "/returns/"];
const PRECACHE_APP_PAGES = ["/activate-owner/","/crm/","/customer-records/","/dashboard/","/debts/","/finance/","/forgot-password/","/hr/","/inventory/","/labels/","/login/","/logs/","/org/","/platform-activity/","/platform-analytics/","/platform-companies/","/platform-errors/","/platform-finance/","/platform-leads/","/platform-plans/","/platform-registrations/","/platform-seo/","/platform-subscriptions/","/platform-team/","/platform-team/member/","/platform/","/purchasing/","/reports/","/reset-password/","/returns/","/sales/","/settings/","/subscription/","/supplier-records/","/track/","/users/","/users/detail/","/web-orders/","/website/"];
// Every hashed chunk, stylesheet and font of this build, plus the manifest
// and icons — filled in at build time from the export.
const PRECACHE_ASSETS = ["/_next/static/chunks/1328-53adf64957863e53.js","/_next/static/chunks/1391-0b93ee9d9f7c21e5.js","/_next/static/chunks/1409-b3ce6e6affad694c.js","/_next/static/chunks/1698-66865647035d1996.js","/_next/static/chunks/182-f26e88b724bd5e6e.js","/_next/static/chunks/2126-608b0a9051caf73e.js","/_next/static/chunks/2785-31913625a873f56c.js","/_next/static/chunks/3117-61a68afb919b8d59.js","/_next/static/chunks/3233-40e2a6e2a5c7ed47.js","/_next/static/chunks/3360-6fc89c9c115a2530.js","/_next/static/chunks/3415-daabf772037de0d5.js","/_next/static/chunks/3995-193cf33b08e91925.js","/_next/static/chunks/4023-49cdbe58402e1f5f.js","/_next/static/chunks/40b91c18-03576e02c01e0947.js","/_next/static/chunks/4265-a68bb7afb1251911.js","/_next/static/chunks/4462.0f420d4f6374ab9b.js","/_next/static/chunks/476-e56912d8c7544d56.js","/_next/static/chunks/4838-398c296d08c00313.js","/_next/static/chunks/5007-1b9c6b33103d8b0e.js","/_next/static/chunks/5405.a2853eec62072dae.js","/_next/static/chunks/5410-087bc64c21c04d17.js","/_next/static/chunks/5811-c5306e37bd205f86.js","/_next/static/chunks/6702-becc1926d1626e66.js","/_next/static/chunks/689-a0465b186118c2fe.js","/_next/static/chunks/694-73d22f93c292b472.js","/_next/static/chunks/7089-af84b523904bfac2.js","/_next/static/chunks/7535-20577c64ca0d6cfa.js","/_next/static/chunks/7536-15fbefc9cc695446.js","/_next/static/chunks/7769-313f6fad97c64c58.js","/_next/static/chunks/7941-e9ce3acebb531c99.js","/_next/static/chunks/7985-048546177220fd36.js","/_next/static/chunks/8199-b7822f9e69122fc5.js","/_next/static/chunks/8288-1bb4dbcffa7aee6f.js","/_next/static/chunks/8430-f929184bb61c728a.js","/_next/static/chunks/8557.bdee3fe4b34fcf91.js","/_next/static/chunks/8690-c9c7775750cdbada.js","/_next/static/chunks/8890-93390470aa87db92.js","/_next/static/chunks/9242-5dadef187f312ae1.js","/_next/static/chunks/9535-13712210b96ba167.js","/_next/static/chunks/9681-44d718ea65c60825.js","/_next/static/chunks/9865-284dd54e354b5acb.js","/_next/static/chunks/app/(app)/crm/page-bff52f536adbae06.js","/_next/static/chunks/app/(app)/customer-records/page-f2ec78841b3d7ef6.js","/_next/static/chunks/app/(app)/dashboard/page-b3418dd3b24c3b7e.js","/_next/static/chunks/app/(app)/debts/page-d220ebfadb0ae140.js","/_next/static/chunks/app/(app)/finance/page-07d544d093a10d3f.js","/_next/static/chunks/app/(app)/hr/page-7c9f03be923bd3be.js","/_next/static/chunks/app/(app)/inventory/page-139810b16e166253.js","/_next/static/chunks/app/(app)/labels/page-e0aff7a37dd8d627.js","/_next/static/chunks/app/(app)/layout-40ba47cab068f292.js","/_next/static/chunks/app/(app)/logs/page-7f3e3a50acbd1047.js","/_next/static/chunks/app/(app)/org/page-693be1e3d250b80c.js","/_next/static/chunks/app/(app)/platform-activity/page-323b8a556671a52f.js","/_next/static/chunks/app/(app)/platform-analytics/page-23c8365582f23a85.js","/_next/static/chunks/app/(app)/platform-companies/page-25ac42e72f9bfceb.js","/_next/static/chunks/app/(app)/platform-errors/page-060312f774f14c8a.js","/_next/static/chunks/app/(app)/platform-finance/page-559c3debdcd64f39.js","/_next/static/chunks/app/(app)/platform-leads/page-65180e72dd21edc4.js","/_next/static/chunks/app/(app)/platform-plans/page-802e2608a9acbfc0.js","/_next/static/chunks/app/(app)/platform-registrations/page-fefc3d49b3b567d8.js","/_next/static/chunks/app/(app)/platform-seo/page-4aa787dca449f3e1.js","/_next/static/chunks/app/(app)/platform-subscriptions/page-59b0da859e9ede74.js","/_next/static/chunks/app/(app)/platform-team/member/page-3fec55a4f9bb01bd.js","/_next/static/chunks/app/(app)/platform-team/page-28ce89eb8c583ac6.js","/_next/static/chunks/app/(app)/platform/page-5e112f76cb23a326.js","/_next/static/chunks/app/(app)/purchasing/page-d940151a889cb8f4.js","/_next/static/chunks/app/(app)/reports/page-0ed61ab56229bded.js","/_next/static/chunks/app/(app)/returns/page-c82b0bd241ac9046.js","/_next/static/chunks/app/(app)/sales/page-d02b37f879eb0c5b.js","/_next/static/chunks/app/(app)/settings/page-7e95c1862607f261.js","/_next/static/chunks/app/(app)/subscription/page-952bb16c599c0cfc.js","/_next/static/chunks/app/(app)/supplier-records/page-0b5be636776ca7e9.js","/_next/static/chunks/app/(app)/users/detail/page-79a80ebf45bd3dc3.js","/_next/static/chunks/app/(app)/users/page-075bea49584394d3.js","/_next/static/chunks/app/(app)/web-orders/page-18aa946bf1734978.js","/_next/static/chunks/app/(app)/website/page-66c73e398e36f02d.js","/_next/static/chunks/app/(marketing)/compare/[slug]/page-b4f17d8c620691de.js","/_next/static/chunks/app/(marketing)/en/compare/[slug]/page-2ae4d0a7158e7429.js","/_next/static/chunks/app/(marketing)/en/guides/[slug]/page-59469ab42647127a.js","/_next/static/chunks/app/(marketing)/en/guides/page-e436aca173e4d8e0.js","/_next/static/chunks/app/(marketing)/en/layout-ddaba7143b3b003d.js","/_next/static/chunks/app/(marketing)/en/page-241a8ba0c6096c6b.js","/_next/static/chunks/app/(marketing)/en/pricing/layout-ddaba7143b3b003d.js","/_next/static/chunks/app/(marketing)/en/pricing/page-926bdc67e49269ba.js","/_next/static/chunks/app/(marketing)/en/product/layout-ddaba7143b3b003d.js","/_next/static/chunks/app/(marketing)/en/product/page-ef919741b812709c.js","/_next/static/chunks/app/(marketing)/en/register/hosting/layout-ddaba7143b3b003d.js","/_next/static/chunks/app/(marketing)/en/register/hosting/page-4c7bc31a2569aa82.js","/_next/static/chunks/app/(marketing)/en/register/layout-ddaba7143b3b003d.js","/_next/static/chunks/app/(marketing)/en/register/page-8fdee7e932eeeb6a.js","/_next/static/chunks/app/(marketing)/en/solutions/[slug]/page-0dd01de2e2bf598d.js","/_next/static/chunks/app/(marketing)/en/solutions/page-9a8269f02ebf71d3.js","/_next/static/chunks/app/(marketing)/en/track/layout-ddaba7143b3b003d.js","/_next/static/chunks/app/(marketing)/en/track/page-e313da7df9b5d12b.js","/_next/static/chunks/app/(marketing)/guides/[slug]/page-e0a272f30b334c8e.js","/_next/static/chunks/app/(marketing)/guides/page-bcb4a3f1bcfc6e27.js","/_next/static/chunks/app/(marketing)/layout-cc6b2782c49ca568.js","/_next/static/chunks/app/(marketing)/page-25e47c221085b3a9.js","/_next/static/chunks/app/(marketing)/pricing/layout-ddaba7143b3b003d.js","/_next/static/chunks/app/(marketing)/pricing/page-4ede9d29ed22e936.js","/_next/static/chunks/app/(marketing)/product/layout-ddaba7143b3b003d.js","/_next/static/chunks/app/(marketing)/product/page-eb9da4dfc6eae837.js","/_next/static/chunks/app/(marketing)/register/hosting/layout-ddaba7143b3b003d.js","/_next/static/chunks/app/(marketing)/register/hosting/page-dd2960e7866d255e.js","/_next/static/chunks/app/(marketing)/register/layout-ddaba7143b3b003d.js","/_next/static/chunks/app/(marketing)/register/page-9e4968833aaa54a3.js","/_next/static/chunks/app/(marketing)/solutions/[slug]/page-9905395906c81fad.js","/_next/static/chunks/app/(marketing)/solutions/page-f9c0871b29aee3c0.js","/_next/static/chunks/app/(marketing)/track/layout-ddaba7143b3b003d.js","/_next/static/chunks/app/(marketing)/track/page-059f84bfbec58aad.js","/_next/static/chunks/app/_not-found/page-93f5ecd9b5a1b8d5.js","/_next/static/chunks/app/activate-owner/layout-3748319e515c6c6b.js","/_next/static/chunks/app/activate-owner/page-e1a123d491ecfdd8.js","/_next/static/chunks/app/forgot-password/layout-3748319e515c6c6b.js","/_next/static/chunks/app/forgot-password/page-cbfecaa3153250bf.js","/_next/static/chunks/app/layout-402b249a037a22cb.js","/_next/static/chunks/app/login/layout-3748319e515c6c6b.js","/_next/static/chunks/app/login/page-42f17408823f70af.js","/_next/static/chunks/app/reset-password/layout-3748319e515c6c6b.js","/_next/static/chunks/app/reset-password/page-adc43c37d4f3e825.js","/_next/static/chunks/app/robots.txt/route-ddaba7143b3b003d.js","/_next/static/chunks/app/sitemap.xml/route-ddaba7143b3b003d.js","/_next/static/chunks/framework-ac871cde7d705c3a.js","/_next/static/chunks/main-61969269e7b3dad5.js","/_next/static/chunks/main-app-d3c2614b980cfab3.js","/_next/static/chunks/pages/_app-c0e3f7ff6ef43cb0.js","/_next/static/chunks/pages/_error-6bf3d2bf6fe2d033.js","/_next/static/chunks/polyfills-42372ed130431b0a.js","/_next/static/chunks/webpack-76fb0d753073358b.js","/_next/static/css/ba3584122835bec0.css","/_next/static/media/011e180705008d6f.woff2","/_next/static/media/19cfc7226ec3afaa.woff2","/_next/static/media/1ebb550cd0a67fc6.p.woff2","/_next/static/media/21350d82a1f187e9.woff2","/_next/static/media/3dc379dc9b5dec12.p.woff2","/_next/static/media/58c726479f69cacd.woff2","/_next/static/media/58f386aa6b1a2a92.woff2","/_next/static/media/63a79a6cf340c5d2.p.woff2","/_next/static/media/7ba5fb2a8c88521c.woff2","/_next/static/media/8e9860b6e62d6359.woff2","/_next/static/media/92eeb95d069020cc.woff2","/_next/static/media/98e207f02528a563.p.woff2","/_next/static/media/99dcf268bda04fe5.woff2","/_next/static/media/ba9851c3c22cd980.woff2","/_next/static/media/bd9c8c62ffadd9dd.p.woff2","/_next/static/media/c5f10e9e72d35c52.woff2","/_next/static/media/c5fe6dc8356a8c31.woff2","/_next/static/media/cc8b755e9c1ba115.woff2","/_next/static/media/ce401babc0566bc1.woff2","/_next/static/media/d29838c109ef09b4.woff2","/_next/static/media/d3ebbfd689654d3a.p.woff2","/_next/static/media/dd994fbf464986f0.p.woff2","/_next/static/media/df0a9ae256c0569c.woff2","/_next/static/media/e40af3453d7c920a.woff2","/_next/static/media/e4af272ccee01ff0.p.woff2","/_next/static/media/e97026df054cf2a3.woff2","/_next/static/media/ef4d5661765d0e49.woff2","/_next/static/media/f15f45d13243c643.woff2","/_next/static/media/f952393b67d608ec.p.woff2","/_next/static/rOEh1Iuh__VTlRhyFwYvK/_buildManifest.js","/_next/static/rOEh1Iuh__VTlRhyFwYvK/_ssgManifest.js","/icons/apple-touch-icon.png","/icons/badge-96.png","/icons/icon-192.png","/icons/icon-512.png","/icons/icon-maskable-192.png","/icons/icon-maskable-512.png","/manifest.webmanifest"];
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
