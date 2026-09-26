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
const BUILD = "IZyMi2yntZubHwyf3m86e";
const CACHE = `vezano-shell-${BUILD}`;
// Every screen of the app, so the person lands on the page they asked for
// with no network — never on a different one. Filled in at build time from
// the export; the list below is the floor the PWA manifest relies on.
const PRECACHE_PAGES = ["/", "/login/", "/dashboard/", "/sales/", "/inventory/", "/returns/"];
const PRECACHE_APP_PAGES = ["/activate-owner/","/crm/","/customer-records/","/dashboard/","/debts/","/finance/","/forgot-password/","/hr/","/inventory/","/labels/","/login/","/logs/","/org/","/platform-activity/","/platform-analytics/","/platform-companies/","/platform-errors/","/platform-finance/","/platform-leads/","/platform-plans/","/platform-registrations/","/platform-seo/","/platform-subscriptions/","/platform-team/","/platform-team/member/","/platform/","/purchasing/","/reports/","/reset-password/","/returns/","/sales/","/settings/","/subscription/","/supplier-records/","/track/","/users/","/users/detail/","/web-orders/","/website/"];
// Every hashed chunk, stylesheet and font of this build, plus the manifest
// and icons — filled in at build time from the export.
const PRECACHE_ASSETS = ["/_next/static/IZyMi2yntZubHwyf3m86e/_buildManifest.js","/_next/static/IZyMi2yntZubHwyf3m86e/_ssgManifest.js","/_next/static/chunks/1328-f61aca8e87377237.js","/_next/static/chunks/1391-0b93ee9d9f7c21e5.js","/_next/static/chunks/2126-ca82e0aaab501f36.js","/_next/static/chunks/2231-f97c2122732716d8.js","/_next/static/chunks/2395-2840df6565c7c063.js","/_next/static/chunks/2757-1881948c9631809d.js","/_next/static/chunks/2811-be5ccf170fc9904d.js","/_next/static/chunks/2901-ea4786a460715b0d.js","/_next/static/chunks/3117-889647130a60a628.js","/_next/static/chunks/3415-13386b5ed295824a.js","/_next/static/chunks/3719-4c167c8a99ff3eb2.js","/_next/static/chunks/3995-193cf33b08e91925.js","/_next/static/chunks/40b91c18-03576e02c01e0947.js","/_next/static/chunks/4200-086e4dd05ced843c.js","/_next/static/chunks/4473-8ea572ad178595e9.js","/_next/static/chunks/4838-379e2894ffa4b949.js","/_next/static/chunks/4883-afcf60389a71db03.js","/_next/static/chunks/5270-e6196d52e65af0b0.js","/_next/static/chunks/5405.a2853eec62072dae.js","/_next/static/chunks/5410-087bc64c21c04d17.js","/_next/static/chunks/5950-90d4cbe9f3c06af8.js","/_next/static/chunks/6055-a246714e6b89cc52.js","/_next/static/chunks/6100-1fc6b211fc806fee.js","/_next/static/chunks/6702-5a33da0ccd8afcac.js","/_next/static/chunks/6762-4eeafa45a2cb5698.js","/_next/static/chunks/7670-1056d442efeb12ab.js","/_next/static/chunks/7769-313f6fad97c64c58.js","/_next/static/chunks/8117-220f357cdf1dced1.js","/_next/static/chunks/8430-f929184bb61c728a.js","/_next/static/chunks/8890-01971f9367d4d1b0.js","/_next/static/chunks/9265-7b58b312cc89db09.js","/_next/static/chunks/9615-3f5e94e8ead3f65b.js","/_next/static/chunks/app/(app)/crm/page-e29e984acf38dd68.js","/_next/static/chunks/app/(app)/customer-records/page-6579fbee25bbb791.js","/_next/static/chunks/app/(app)/dashboard/page-486d3251a5580022.js","/_next/static/chunks/app/(app)/debts/page-f191eb90fd3434e9.js","/_next/static/chunks/app/(app)/finance/page-5bc7ffc4f9d283f3.js","/_next/static/chunks/app/(app)/hr/page-a757ef28f320f3e0.js","/_next/static/chunks/app/(app)/inventory/page-0ab7d525743ba951.js","/_next/static/chunks/app/(app)/labels/page-54bdb8e6eb707bb9.js","/_next/static/chunks/app/(app)/layout-f761ced597eae1e0.js","/_next/static/chunks/app/(app)/logs/page-600f18d12f250cab.js","/_next/static/chunks/app/(app)/org/page-d7969ffa43baa8e8.js","/_next/static/chunks/app/(app)/platform-activity/page-dbb754c3609466a1.js","/_next/static/chunks/app/(app)/platform-analytics/page-12de048e822a48df.js","/_next/static/chunks/app/(app)/platform-companies/page-2c9e7aa38189ddf5.js","/_next/static/chunks/app/(app)/platform-errors/page-2fe8a44222ef8fff.js","/_next/static/chunks/app/(app)/platform-finance/page-cbc023204640c1f8.js","/_next/static/chunks/app/(app)/platform-leads/page-05f3d36ff85e25fc.js","/_next/static/chunks/app/(app)/platform-plans/page-db6b53c51a49fce8.js","/_next/static/chunks/app/(app)/platform-registrations/page-7605cbee54b11dcd.js","/_next/static/chunks/app/(app)/platform-seo/page-06aee5a9388ea2a0.js","/_next/static/chunks/app/(app)/platform-subscriptions/page-acc8132b3a904399.js","/_next/static/chunks/app/(app)/platform-team/member/page-de45e9a9811422bd.js","/_next/static/chunks/app/(app)/platform-team/page-12a5d93b348a7278.js","/_next/static/chunks/app/(app)/platform/page-95e617703f9ce439.js","/_next/static/chunks/app/(app)/purchasing/page-05fa3b4c248955e9.js","/_next/static/chunks/app/(app)/reports/page-575ed33d20c21cc4.js","/_next/static/chunks/app/(app)/returns/page-ec6df8c501cb91d9.js","/_next/static/chunks/app/(app)/sales/page-e859b3f1b7e618d7.js","/_next/static/chunks/app/(app)/settings/page-d8e5c2e580235eff.js","/_next/static/chunks/app/(app)/subscription/page-fad923e1996e260a.js","/_next/static/chunks/app/(app)/supplier-records/page-2bbbd0d887dcdcf0.js","/_next/static/chunks/app/(app)/users/detail/page-b6524404ac1dc165.js","/_next/static/chunks/app/(app)/users/page-68156a14f151f665.js","/_next/static/chunks/app/(app)/web-orders/page-52f735bdf991e808.js","/_next/static/chunks/app/(app)/website/page-358a4ade6b8f4899.js","/_next/static/chunks/app/(marketing)/compare/[slug]/page-067739cb7af8fbbd.js","/_next/static/chunks/app/(marketing)/en/compare/[slug]/page-d0e8b6c8b708262c.js","/_next/static/chunks/app/(marketing)/en/guides/[slug]/page-35698c7aaab6e19c.js","/_next/static/chunks/app/(marketing)/en/guides/page-9deefe5b30e5ce34.js","/_next/static/chunks/app/(marketing)/en/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/en/page-799a1f088e6594dd.js","/_next/static/chunks/app/(marketing)/en/pricing/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/en/pricing/page-08c27ea603364dba.js","/_next/static/chunks/app/(marketing)/en/product/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/en/product/page-23de8595f6ec89e6.js","/_next/static/chunks/app/(marketing)/en/register/hosting/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/en/register/hosting/page-eeeed5c851a7b6b3.js","/_next/static/chunks/app/(marketing)/en/register/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/en/register/page-41bfa69b002ab1cf.js","/_next/static/chunks/app/(marketing)/en/solutions/[slug]/page-1f45c7345b99ba80.js","/_next/static/chunks/app/(marketing)/en/solutions/page-e86be18304e4c328.js","/_next/static/chunks/app/(marketing)/en/track/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/en/track/page-2b8daec6ba7bdef7.js","/_next/static/chunks/app/(marketing)/guides/[slug]/page-43b0def53ed14e08.js","/_next/static/chunks/app/(marketing)/guides/page-aa3e9ec93bcba914.js","/_next/static/chunks/app/(marketing)/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/page-9200dc954e1412eb.js","/_next/static/chunks/app/(marketing)/pricing/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/pricing/page-891dbfce2a0c4015.js","/_next/static/chunks/app/(marketing)/product/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/product/page-e4d6da0ee43ec940.js","/_next/static/chunks/app/(marketing)/register/hosting/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/register/hosting/page-468a520f156a217c.js","/_next/static/chunks/app/(marketing)/register/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/register/page-d967ef018edf4019.js","/_next/static/chunks/app/(marketing)/solutions/[slug]/page-107377dc82b486e9.js","/_next/static/chunks/app/(marketing)/solutions/page-8aea6537ed73c589.js","/_next/static/chunks/app/(marketing)/track/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/track/page-1b316677634efa82.js","/_next/static/chunks/app/_not-found/page-93f5ecd9b5a1b8d5.js","/_next/static/chunks/app/activate-owner/layout-9111370ccccd4922.js","/_next/static/chunks/app/activate-owner/page-8ac84b1a6d00f625.js","/_next/static/chunks/app/forgot-password/layout-9111370ccccd4922.js","/_next/static/chunks/app/forgot-password/page-72bf70b92ab075ce.js","/_next/static/chunks/app/layout-1022e874d02fa815.js","/_next/static/chunks/app/login/layout-9111370ccccd4922.js","/_next/static/chunks/app/login/page-81d89fafd521c538.js","/_next/static/chunks/app/reset-password/layout-9111370ccccd4922.js","/_next/static/chunks/app/reset-password/page-6c705d028dc19ff8.js","/_next/static/chunks/app/robots.txt/route-9111370ccccd4922.js","/_next/static/chunks/app/sitemap.xml/route-9111370ccccd4922.js","/_next/static/chunks/framework-ac871cde7d705c3a.js","/_next/static/chunks/main-61969269e7b3dad5.js","/_next/static/chunks/main-app-d3c2614b980cfab3.js","/_next/static/chunks/pages/_app-c0e3f7ff6ef43cb0.js","/_next/static/chunks/pages/_error-6bf3d2bf6fe2d033.js","/_next/static/chunks/polyfills-42372ed130431b0a.js","/_next/static/chunks/webpack-91ffaed1d638f79f.js","/_next/static/css/81127cc7577d128a.css","/_next/static/media/011e180705008d6f-s.woff2","/_next/static/media/19cfc7226ec3afaa-s.woff2","/_next/static/media/1ebb550cd0a67fc6-s.p.woff2","/_next/static/media/21350d82a1f187e9-s.woff2","/_next/static/media/3dc379dc9b5dec12-s.p.woff2","/_next/static/media/58c726479f69cacd-s.woff2","/_next/static/media/58f386aa6b1a2a92-s.woff2","/_next/static/media/63a79a6cf340c5d2-s.p.woff2","/_next/static/media/7ba5fb2a8c88521c-s.woff2","/_next/static/media/8e9860b6e62d6359-s.woff2","/_next/static/media/92eeb95d069020cc-s.woff2","/_next/static/media/98e207f02528a563-s.p.woff2","/_next/static/media/99dcf268bda04fe5-s.woff2","/_next/static/media/ba9851c3c22cd980-s.woff2","/_next/static/media/bd9c8c62ffadd9dd-s.p.woff2","/_next/static/media/c5f10e9e72d35c52-s.woff2","/_next/static/media/c5fe6dc8356a8c31-s.woff2","/_next/static/media/cc8b755e9c1ba115-s.woff2","/_next/static/media/ce401babc0566bc1-s.woff2","/_next/static/media/d29838c109ef09b4-s.woff2","/_next/static/media/d3ebbfd689654d3a-s.p.woff2","/_next/static/media/dd994fbf464986f0-s.p.woff2","/_next/static/media/df0a9ae256c0569c-s.woff2","/_next/static/media/e40af3453d7c920a-s.woff2","/_next/static/media/e4af272ccee01ff0-s.p.woff2","/_next/static/media/e97026df054cf2a3-s.woff2","/_next/static/media/ef4d5661765d0e49-s.woff2","/_next/static/media/f15f45d13243c643-s.woff2","/_next/static/media/f952393b67d608ec-s.p.woff2","/icons/apple-touch-icon.png","/icons/badge-96.png","/icons/icon-192.png","/icons/icon-512.png","/icons/icon-maskable-192.png","/icons/icon-maskable-512.png","/manifest.webmanifest"];
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
