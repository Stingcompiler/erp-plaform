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
const BUILD = "bz72ZVx4yJiZzp1l-sHzp";
const CACHE = `vezano-shell-${BUILD}`;
// Every screen of the app, so the person lands on the page they asked for
// with no network — never on a different one. Filled in at build time from
// the export; the list below is the floor the PWA manifest relies on.
const PRECACHE_PAGES = ["/", "/login/", "/dashboard/", "/sales/", "/inventory/", "/returns/"];
const PRECACHE_APP_PAGES = ["/activate-owner/","/crm/","/customer-records/","/dashboard/","/debts/","/finance/","/forgot-password/","/hr/","/inventory/","/labels/","/login/","/logs/","/org/","/platform-activity/","/platform-analytics/","/platform-companies/","/platform-errors/","/platform-finance/","/platform-leads/","/platform-plans/","/platform-registrations/","/platform-seo/","/platform-subscriptions/","/platform-team/","/platform-team/member/","/platform/","/purchasing/","/reports/","/reset-password/","/returns/","/sales/","/settings/","/subscription/","/supplier-records/","/track/","/users/","/users/detail/","/web-orders/","/website/"];
// Every hashed chunk, stylesheet and font of this build, plus the manifest
// and icons — filled in at build time from the export.
const PRECACHE_ASSETS = ["/_next/static/bz72ZVx4yJiZzp1l-sHzp/_buildManifest.js","/_next/static/bz72ZVx4yJiZzp1l-sHzp/_ssgManifest.js","/_next/static/chunks/1328-f61aca8e87377237.js","/_next/static/chunks/1391-0b93ee9d9f7c21e5.js","/_next/static/chunks/1409-05db44ab90a94f3e.js","/_next/static/chunks/1698-66865647035d1996.js","/_next/static/chunks/2126-7b7217b357a0cfb8.js","/_next/static/chunks/2785-a68209e77807df85.js","/_next/static/chunks/2901-52934b8086809ce1.js","/_next/static/chunks/3117-779e968607fe2cc6.js","/_next/static/chunks/3360-df2a082072b5c60d.js","/_next/static/chunks/3415-d4747b3a11254a27.js","/_next/static/chunks/3995-193cf33b08e91925.js","/_next/static/chunks/4023-df0da7eb8906d449.js","/_next/static/chunks/40b91c18-03576e02c01e0947.js","/_next/static/chunks/4200-086e4dd05ced843c.js","/_next/static/chunks/4265-6b8e540634aefe6a.js","/_next/static/chunks/4462.0f420d4f6374ab9b.js","/_next/static/chunks/4641-e24d27ed90959235.js","/_next/static/chunks/476-91a03d2926c4bb1d.js","/_next/static/chunks/4838-398c296d08c00313.js","/_next/static/chunks/4987-f5217d263617db1a.js","/_next/static/chunks/5405.a2853eec62072dae.js","/_next/static/chunks/5410-087bc64c21c04d17.js","/_next/static/chunks/5811-80eec4e97ff01b4d.js","/_next/static/chunks/6702-5a33da0ccd8afcac.js","/_next/static/chunks/689-f7c6c557b5809682.js","/_next/static/chunks/694-73d22f93c292b472.js","/_next/static/chunks/7089-af84b523904bfac2.js","/_next/static/chunks/7536-15fbefc9cc695446.js","/_next/static/chunks/7769-313f6fad97c64c58.js","/_next/static/chunks/7941-031dfbdd1ceafa77.js","/_next/static/chunks/7985-d1895cf41b593f2a.js","/_next/static/chunks/8199-bd61374336f60601.js","/_next/static/chunks/8288-47bfec66ded80bcb.js","/_next/static/chunks/8430-f929184bb61c728a.js","/_next/static/chunks/8557.bdee3fe4b34fcf91.js","/_next/static/chunks/8873-18eda7c07e488696.js","/_next/static/chunks/8890-e380b3deefae36d0.js","/_next/static/chunks/9242-8b7238ca5f101a62.js","/_next/static/chunks/9681-f7fe59c4baa9d55d.js","/_next/static/chunks/9865-4a519997c0fdc178.js","/_next/static/chunks/app/(app)/crm/page-38c01680c95b2091.js","/_next/static/chunks/app/(app)/customer-records/page-2286e767b3073092.js","/_next/static/chunks/app/(app)/dashboard/page-37c313bc42a32a10.js","/_next/static/chunks/app/(app)/debts/page-0da2ab0355d30c21.js","/_next/static/chunks/app/(app)/finance/page-06082f8ee5b7f87c.js","/_next/static/chunks/app/(app)/hr/page-837b961d41eb1e71.js","/_next/static/chunks/app/(app)/inventory/page-9ca4f7c28b0f2ac7.js","/_next/static/chunks/app/(app)/labels/page-52adf4d4aa9871db.js","/_next/static/chunks/app/(app)/layout-3e8f6788e4fed92c.js","/_next/static/chunks/app/(app)/logs/page-d62252168aa39141.js","/_next/static/chunks/app/(app)/org/page-b043f3fc4115caf6.js","/_next/static/chunks/app/(app)/platform-activity/page-ccbe8c371e2deacb.js","/_next/static/chunks/app/(app)/platform-analytics/page-ed9d9a01da33cf72.js","/_next/static/chunks/app/(app)/platform-companies/page-794ec8d48e1d6bea.js","/_next/static/chunks/app/(app)/platform-errors/page-17ee423398dbf16a.js","/_next/static/chunks/app/(app)/platform-finance/page-b01be19932f3b8cf.js","/_next/static/chunks/app/(app)/platform-leads/page-4fc560e1926ebb4a.js","/_next/static/chunks/app/(app)/platform-plans/page-647cf2a35a0399f4.js","/_next/static/chunks/app/(app)/platform-registrations/page-cdba844737bba82b.js","/_next/static/chunks/app/(app)/platform-seo/page-c3f71b3b5e1c6bbd.js","/_next/static/chunks/app/(app)/platform-subscriptions/page-c793cb4d5a0d45c1.js","/_next/static/chunks/app/(app)/platform-team/member/page-a74840cab56e25c8.js","/_next/static/chunks/app/(app)/platform-team/page-0b370f847601b156.js","/_next/static/chunks/app/(app)/platform/page-53e50392e10e38f9.js","/_next/static/chunks/app/(app)/purchasing/page-778891a3e20e6162.js","/_next/static/chunks/app/(app)/reports/page-368db396d0d18d9b.js","/_next/static/chunks/app/(app)/returns/page-d287f0d1295a87db.js","/_next/static/chunks/app/(app)/sales/page-60c546e94f59e10d.js","/_next/static/chunks/app/(app)/settings/page-2734ce47becc70df.js","/_next/static/chunks/app/(app)/subscription/page-335f1e40022c0905.js","/_next/static/chunks/app/(app)/supplier-records/page-00dd7beb4a9f3f21.js","/_next/static/chunks/app/(app)/users/detail/page-76420fb1329b185c.js","/_next/static/chunks/app/(app)/users/page-e95628896a380ead.js","/_next/static/chunks/app/(app)/web-orders/page-f270a85a9718ae62.js","/_next/static/chunks/app/(app)/website/page-cbba3b2c9a0b0e52.js","/_next/static/chunks/app/(marketing)/compare/[slug]/page-ff7e1a5251e15147.js","/_next/static/chunks/app/(marketing)/en/compare/[slug]/page-b59a9454dc440002.js","/_next/static/chunks/app/(marketing)/en/guides/[slug]/page-903431c260e5cc74.js","/_next/static/chunks/app/(marketing)/en/guides/page-0168ab57e97f5043.js","/_next/static/chunks/app/(marketing)/en/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/en/page-48fa03980e1d8a97.js","/_next/static/chunks/app/(marketing)/en/pricing/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/en/pricing/page-3abce0bd0569e404.js","/_next/static/chunks/app/(marketing)/en/product/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/en/product/page-99b5707aaf52668f.js","/_next/static/chunks/app/(marketing)/en/register/hosting/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/en/register/hosting/page-7d67c889224c0f39.js","/_next/static/chunks/app/(marketing)/en/register/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/en/register/page-6d71bb7ef8480d64.js","/_next/static/chunks/app/(marketing)/en/solutions/[slug]/page-cc26d59c8e25c013.js","/_next/static/chunks/app/(marketing)/en/solutions/page-b7ed85652b8b76df.js","/_next/static/chunks/app/(marketing)/en/track/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/en/track/page-5014876a6eae209a.js","/_next/static/chunks/app/(marketing)/guides/[slug]/page-b55906ba0ef75968.js","/_next/static/chunks/app/(marketing)/guides/page-7158ba5152d0aec9.js","/_next/static/chunks/app/(marketing)/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/page-e05e087becf8dc68.js","/_next/static/chunks/app/(marketing)/pricing/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/pricing/page-a3b7695a2ae9f040.js","/_next/static/chunks/app/(marketing)/product/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/product/page-a82b3896d67ac73e.js","/_next/static/chunks/app/(marketing)/register/hosting/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/register/hosting/page-5269ac55d092a648.js","/_next/static/chunks/app/(marketing)/register/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/register/page-6bcdc0c198751878.js","/_next/static/chunks/app/(marketing)/solutions/[slug]/page-ea80bf5f2734e0c1.js","/_next/static/chunks/app/(marketing)/solutions/page-9cec45d927d7b896.js","/_next/static/chunks/app/(marketing)/track/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/track/page-8b9b213bbc44d1f4.js","/_next/static/chunks/app/_not-found/page-93f5ecd9b5a1b8d5.js","/_next/static/chunks/app/activate-owner/layout-9111370ccccd4922.js","/_next/static/chunks/app/activate-owner/page-1a5458e9ac453625.js","/_next/static/chunks/app/forgot-password/layout-9111370ccccd4922.js","/_next/static/chunks/app/forgot-password/page-b76181d6e6fe54ee.js","/_next/static/chunks/app/layout-1e803e5993dc680d.js","/_next/static/chunks/app/login/layout-9111370ccccd4922.js","/_next/static/chunks/app/login/page-e101ef543689d40c.js","/_next/static/chunks/app/reset-password/layout-9111370ccccd4922.js","/_next/static/chunks/app/reset-password/page-dbe2eede8b4c6cae.js","/_next/static/chunks/app/robots.txt/route-9111370ccccd4922.js","/_next/static/chunks/app/sitemap.xml/route-9111370ccccd4922.js","/_next/static/chunks/framework-ac871cde7d705c3a.js","/_next/static/chunks/main-61969269e7b3dad5.js","/_next/static/chunks/main-app-d3c2614b980cfab3.js","/_next/static/chunks/pages/_app-c0e3f7ff6ef43cb0.js","/_next/static/chunks/pages/_error-6bf3d2bf6fe2d033.js","/_next/static/chunks/polyfills-42372ed130431b0a.js","/_next/static/chunks/webpack-76fb0d753073358b.js","/_next/static/css/0d4113adffe4e629.css","/_next/static/media/011e180705008d6f.woff2","/_next/static/media/19cfc7226ec3afaa.woff2","/_next/static/media/1ebb550cd0a67fc6.p.woff2","/_next/static/media/21350d82a1f187e9.woff2","/_next/static/media/3dc379dc9b5dec12.p.woff2","/_next/static/media/58c726479f69cacd.woff2","/_next/static/media/58f386aa6b1a2a92.woff2","/_next/static/media/63a79a6cf340c5d2.p.woff2","/_next/static/media/7ba5fb2a8c88521c.woff2","/_next/static/media/8e9860b6e62d6359.woff2","/_next/static/media/92eeb95d069020cc.woff2","/_next/static/media/98e207f02528a563.p.woff2","/_next/static/media/99dcf268bda04fe5.woff2","/_next/static/media/ba9851c3c22cd980.woff2","/_next/static/media/bd9c8c62ffadd9dd.p.woff2","/_next/static/media/c5f10e9e72d35c52.woff2","/_next/static/media/c5fe6dc8356a8c31.woff2","/_next/static/media/cc8b755e9c1ba115.woff2","/_next/static/media/ce401babc0566bc1.woff2","/_next/static/media/d29838c109ef09b4.woff2","/_next/static/media/d3ebbfd689654d3a.p.woff2","/_next/static/media/dd994fbf464986f0.p.woff2","/_next/static/media/df0a9ae256c0569c.woff2","/_next/static/media/e40af3453d7c920a.woff2","/_next/static/media/e4af272ccee01ff0.p.woff2","/_next/static/media/e97026df054cf2a3.woff2","/_next/static/media/ef4d5661765d0e49.woff2","/_next/static/media/f15f45d13243c643.woff2","/_next/static/media/f952393b67d608ec.p.woff2","/icons/apple-touch-icon.png","/icons/badge-96.png","/icons/icon-192.png","/icons/icon-512.png","/icons/icon-maskable-192.png","/icons/icon-maskable-512.png","/manifest.webmanifest"];
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
