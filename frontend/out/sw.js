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
const BUILD = "JDl46SSqcm3zFZQCuT-X1";
const CACHE = `vezano-shell-${BUILD}`;
// Every screen of the app, so the person lands on the page they asked for
// with no network — never on a different one. Filled in at build time from
// the export; the list below is the floor the PWA manifest relies on.
const PRECACHE_PAGES = ["/", "/login/", "/dashboard/", "/sales/", "/inventory/", "/returns/"];
const PRECACHE_APP_PAGES = ["/activate-owner/","/crm/","/customer-records/","/dashboard/","/debts/","/finance/","/forgot-password/","/hr/","/inventory/","/labels/","/login/","/logs/","/org/","/platform-activity/","/platform-analytics/","/platform-companies/","/platform-errors/","/platform-finance/","/platform-leads/","/platform-plans/","/platform-registrations/","/platform-seo/","/platform-subscriptions/","/platform-team/","/platform-team/member/","/platform/","/purchasing/","/reports/","/reset-password/","/returns/","/sales/","/settings/","/subscription/","/supplier-records/","/users/","/users/detail/","/web-orders/","/website/"];
// Every hashed chunk, stylesheet and font of this build, plus the manifest
// and icons — filled in at build time from the export.
const PRECACHE_ASSETS = ["/_next/static/JDl46SSqcm3zFZQCuT-X1/_buildManifest.js","/_next/static/JDl46SSqcm3zFZQCuT-X1/_ssgManifest.js","/_next/static/chunks/1391-0b93ee9d9f7c21e5.js","/_next/static/chunks/2126-1acdac055fac4f83.js","/_next/static/chunks/2231-bf97c83a39c12487.js","/_next/static/chunks/2395-2840df6565c7c063.js","/_next/static/chunks/2901-3875332172fdaf5d.js","/_next/static/chunks/3415-3b52657d629685c3.js","/_next/static/chunks/3719-8637407c9cdd483d.js","/_next/static/chunks/3995-193cf33b08e91925.js","/_next/static/chunks/40b91c18-03576e02c01e0947.js","/_next/static/chunks/4200-086e4dd05ced843c.js","/_next/static/chunks/4473-a9c40f7d5b36fc60.js","/_next/static/chunks/4838-379e2894ffa4b949.js","/_next/static/chunks/5270-5524ca512562f1a0.js","/_next/static/chunks/5405.a2853eec62072dae.js","/_next/static/chunks/5410-087bc64c21c04d17.js","/_next/static/chunks/5950-fcc1b30d0065d532.js","/_next/static/chunks/6055-fd695756aec085b1.js","/_next/static/chunks/6100-1fc6b211fc806fee.js","/_next/static/chunks/6195-a72507a58c25e6da.js","/_next/static/chunks/6702-5a33da0ccd8afcac.js","/_next/static/chunks/6762-95e6208864c53649.js","/_next/static/chunks/7670-1056d442efeb12ab.js","/_next/static/chunks/7769-313f6fad97c64c58.js","/_next/static/chunks/8059-387628fc4803be95.js","/_next/static/chunks/8117-8853c01fb575d9f0.js","/_next/static/chunks/8430-f929184bb61c728a.js","/_next/static/chunks/8890-f5f922f1f2377857.js","/_next/static/chunks/9168-d05e34c5227b0c56.js","/_next/static/chunks/9265-7b58b312cc89db09.js","/_next/static/chunks/9615-f70fb75953e94f64.js","/_next/static/chunks/app/(app)/crm/page-9543ab77c3238e5a.js","/_next/static/chunks/app/(app)/customer-records/page-ce0420985abe9ed6.js","/_next/static/chunks/app/(app)/dashboard/page-4764c0cbd4145964.js","/_next/static/chunks/app/(app)/debts/page-dbc1c6a23e5e3e61.js","/_next/static/chunks/app/(app)/finance/page-a02256915e5aef89.js","/_next/static/chunks/app/(app)/hr/page-24a6d38d43496a49.js","/_next/static/chunks/app/(app)/inventory/page-c36741bd2da63728.js","/_next/static/chunks/app/(app)/labels/page-c112341f336a2dba.js","/_next/static/chunks/app/(app)/layout-1daa2734bcdb9898.js","/_next/static/chunks/app/(app)/logs/page-683b48028a14a277.js","/_next/static/chunks/app/(app)/org/page-26c9e76a96e040f7.js","/_next/static/chunks/app/(app)/platform-activity/page-fbca4f16d5326763.js","/_next/static/chunks/app/(app)/platform-analytics/page-f624683b4a6c5a16.js","/_next/static/chunks/app/(app)/platform-companies/page-412fe6a11b545a7d.js","/_next/static/chunks/app/(app)/platform-errors/page-cf9703586a7eb815.js","/_next/static/chunks/app/(app)/platform-finance/page-4adaa52e089826bf.js","/_next/static/chunks/app/(app)/platform-leads/page-93a3c0c1fd620121.js","/_next/static/chunks/app/(app)/platform-plans/page-bd1ad519956cf197.js","/_next/static/chunks/app/(app)/platform-registrations/page-ff56d0f8abc8a42e.js","/_next/static/chunks/app/(app)/platform-seo/page-491d2613263f1982.js","/_next/static/chunks/app/(app)/platform-subscriptions/page-78c8e909af6c75aa.js","/_next/static/chunks/app/(app)/platform-team/member/page-3d48e87235e19efa.js","/_next/static/chunks/app/(app)/platform-team/page-0303f2c289cfbc23.js","/_next/static/chunks/app/(app)/platform/page-5f7722353f6b60c6.js","/_next/static/chunks/app/(app)/purchasing/page-2aa59b514dac6d9e.js","/_next/static/chunks/app/(app)/reports/page-92c181e86260befd.js","/_next/static/chunks/app/(app)/returns/page-0f09fbee16e5ff65.js","/_next/static/chunks/app/(app)/sales/page-89dbc89a99d4241e.js","/_next/static/chunks/app/(app)/settings/page-b3c535109bb37914.js","/_next/static/chunks/app/(app)/subscription/page-d44a1dec34c47296.js","/_next/static/chunks/app/(app)/supplier-records/page-abc75c913957d96c.js","/_next/static/chunks/app/(app)/users/detail/page-bffb4807b98e9913.js","/_next/static/chunks/app/(app)/users/page-3b076f16c54967c1.js","/_next/static/chunks/app/(app)/web-orders/page-754dbfe8b861cca0.js","/_next/static/chunks/app/(app)/website/page-d9332907de266d97.js","/_next/static/chunks/app/(marketing)/compare/[slug]/page-15a22bf9d5e6db0e.js","/_next/static/chunks/app/(marketing)/en/compare/[slug]/page-7c29d5354304e80d.js","/_next/static/chunks/app/(marketing)/en/guides/[slug]/page-da0e1723bf1529bf.js","/_next/static/chunks/app/(marketing)/en/guides/page-a203d9bfb735c274.js","/_next/static/chunks/app/(marketing)/en/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/en/page-cd41055c3dbe0390.js","/_next/static/chunks/app/(marketing)/en/pricing/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/en/pricing/page-32a988dc9fe82ea8.js","/_next/static/chunks/app/(marketing)/en/product/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/en/product/page-9650a6bb112603ff.js","/_next/static/chunks/app/(marketing)/en/register/hosting/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/en/register/hosting/page-bbfd73f241bd3efd.js","/_next/static/chunks/app/(marketing)/en/register/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/en/register/page-cae2fd868ea21660.js","/_next/static/chunks/app/(marketing)/en/solutions/[slug]/page-a003c8ede95a29c3.js","/_next/static/chunks/app/(marketing)/en/solutions/page-4253dcdd409b793b.js","/_next/static/chunks/app/(marketing)/guides/[slug]/page-79dd419e96837f50.js","/_next/static/chunks/app/(marketing)/guides/page-dc6fa3e2302566b7.js","/_next/static/chunks/app/(marketing)/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/page-b65275a82a78417c.js","/_next/static/chunks/app/(marketing)/pricing/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/pricing/page-3e63f56811faf982.js","/_next/static/chunks/app/(marketing)/product/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/product/page-9cc7ce9c7c442215.js","/_next/static/chunks/app/(marketing)/register/hosting/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/register/hosting/page-04d5216641778e68.js","/_next/static/chunks/app/(marketing)/register/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/register/page-97b8d190f19f2941.js","/_next/static/chunks/app/(marketing)/solutions/[slug]/page-2e207cf69c17b956.js","/_next/static/chunks/app/(marketing)/solutions/page-c2024ca02e63cb99.js","/_next/static/chunks/app/_not-found/page-93f5ecd9b5a1b8d5.js","/_next/static/chunks/app/activate-owner/layout-163c837417bd2db7.js","/_next/static/chunks/app/activate-owner/page-7249a7e244520151.js","/_next/static/chunks/app/forgot-password/layout-163c837417bd2db7.js","/_next/static/chunks/app/forgot-password/page-a855bd6ee17f4bab.js","/_next/static/chunks/app/layout-97756640d601e292.js","/_next/static/chunks/app/login/layout-163c837417bd2db7.js","/_next/static/chunks/app/login/page-277eba6edb4a0f18.js","/_next/static/chunks/app/reset-password/layout-163c837417bd2db7.js","/_next/static/chunks/app/reset-password/page-0977c9444f0c7419.js","/_next/static/chunks/app/robots.txt/route-163c837417bd2db7.js","/_next/static/chunks/app/sitemap.xml/route-163c837417bd2db7.js","/_next/static/chunks/framework-ac871cde7d705c3a.js","/_next/static/chunks/main-61969269e7b3dad5.js","/_next/static/chunks/main-app-d3c2614b980cfab3.js","/_next/static/chunks/pages/_app-c0e3f7ff6ef43cb0.js","/_next/static/chunks/pages/_error-6bf3d2bf6fe2d033.js","/_next/static/chunks/polyfills-42372ed130431b0a.js","/_next/static/chunks/webpack-2e36f40915576872.js","/_next/static/css/bc236957e4c6c615.css","/_next/static/media/011e180705008d6f-s.woff2","/_next/static/media/19cfc7226ec3afaa-s.woff2","/_next/static/media/1ebb550cd0a67fc6-s.p.woff2","/_next/static/media/21350d82a1f187e9-s.woff2","/_next/static/media/3dc379dc9b5dec12-s.p.woff2","/_next/static/media/58f386aa6b1a2a92-s.woff2","/_next/static/media/63a79a6cf340c5d2-s.p.woff2","/_next/static/media/7ba5fb2a8c88521c-s.woff2","/_next/static/media/8e9860b6e62d6359-s.woff2","/_next/static/media/92eeb95d069020cc-s.woff2","/_next/static/media/98e207f02528a563-s.p.woff2","/_next/static/media/99dcf268bda04fe5-s.woff2","/_next/static/media/ba9851c3c22cd980-s.woff2","/_next/static/media/c5f10e9e72d35c52-s.woff2","/_next/static/media/c5fe6dc8356a8c31-s.woff2","/_next/static/media/ce401babc0566bc1-s.woff2","/_next/static/media/d29838c109ef09b4-s.woff2","/_next/static/media/d3ebbfd689654d3a-s.p.woff2","/_next/static/media/dd994fbf464986f0-s.p.woff2","/_next/static/media/df0a9ae256c0569c-s.woff2","/_next/static/media/e40af3453d7c920a-s.woff2","/_next/static/media/e4af272ccee01ff0-s.p.woff2","/_next/static/media/e97026df054cf2a3-s.woff2","/_next/static/media/ef4d5661765d0e49-s.woff2","/_next/static/media/f15f45d13243c643-s.woff2","/icons/apple-touch-icon.png","/icons/icon-192.png","/icons/icon-512.png","/icons/icon-maskable-192.png","/icons/icon-maskable-512.png","/manifest.webmanifest"];
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
