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
const BUILD = "WhONa-6m-mf-ChKMAnrJ4";
const CACHE = `vezano-shell-${BUILD}`;
// Every screen of the app, so the person lands on the page they asked for
// with no network — never on a different one. Filled in at build time from
// the export; the list below is the floor the PWA manifest relies on.
const PRECACHE_PAGES = ["/", "/login/", "/dashboard/", "/sales/", "/inventory/", "/returns/"];
const PRECACHE_APP_PAGES = ["/activate-owner/","/crm/","/customer-records/","/dashboard/","/debts/","/finance/","/forgot-password/","/hr/","/inventory/","/labels/","/login/","/logs/","/org/","/platform-activity/","/platform-analytics/","/platform-companies/","/platform-errors/","/platform-finance/","/platform-leads/","/platform-plans/","/platform-registrations/","/platform-seo/","/platform-subscriptions/","/platform-team/","/platform-team/member/","/platform/","/purchasing/","/reports/","/reset-password/","/returns/","/sales/","/settings/","/subscription/","/supplier-records/","/users/","/users/detail/","/web-orders/","/website/"];
// Every hashed chunk, stylesheet and font of this build, plus the manifest
// and icons — filled in at build time from the export.
const PRECACHE_ASSETS = ["/_next/static/WhONa-6m-mf-ChKMAnrJ4/_buildManifest.js","/_next/static/WhONa-6m-mf-ChKMAnrJ4/_ssgManifest.js","/_next/static/chunks/1391-0b93ee9d9f7c21e5.js","/_next/static/chunks/2126-d8ba67c1bb54e773.js","/_next/static/chunks/2395-2840df6565c7c063.js","/_next/static/chunks/2901-8dffa7f1c2e12eec.js","/_next/static/chunks/3378-930d9e31beb75a69.js","/_next/static/chunks/3415-63dd53a3d27d33dd.js","/_next/static/chunks/3719-8637407c9cdd483d.js","/_next/static/chunks/3995-193cf33b08e91925.js","/_next/static/chunks/40b91c18-03576e02c01e0947.js","/_next/static/chunks/4200-086e4dd05ced843c.js","/_next/static/chunks/4473-a9c40f7d5b36fc60.js","/_next/static/chunks/4838-379e2894ffa4b949.js","/_next/static/chunks/5127-8ce8e51bca0fc7a3.js","/_next/static/chunks/5270-fd78028256dbaba0.js","/_next/static/chunks/5405.a2853eec62072dae.js","/_next/static/chunks/5410-087bc64c21c04d17.js","/_next/static/chunks/5950-b6379abbc401e4c6.js","/_next/static/chunks/6055-fd695756aec085b1.js","/_next/static/chunks/6195-a72507a58c25e6da.js","/_next/static/chunks/6702-5a33da0ccd8afcac.js","/_next/static/chunks/6762-40c7f3913fa9e349.js","/_next/static/chunks/7655-08864f5cb6e1255d.js","/_next/static/chunks/7670-1056d442efeb12ab.js","/_next/static/chunks/7733-a48a609e5b8d8a1f.js","/_next/static/chunks/7769-313f6fad97c64c58.js","/_next/static/chunks/8117-14aa7bf52432c1b3.js","/_next/static/chunks/8430-f929184bb61c728a.js","/_next/static/chunks/9168-d05e34c5227b0c56.js","/_next/static/chunks/9265-7b58b312cc89db09.js","/_next/static/chunks/9615-f70fb75953e94f64.js","/_next/static/chunks/app/(app)/crm/page-999845c63aab61fb.js","/_next/static/chunks/app/(app)/customer-records/page-e1ef1ef4d14e84a1.js","/_next/static/chunks/app/(app)/dashboard/page-2d314ac43f8403da.js","/_next/static/chunks/app/(app)/debts/page-9bb6ebb3cf9603e4.js","/_next/static/chunks/app/(app)/finance/page-ea9d1b452f441bb3.js","/_next/static/chunks/app/(app)/hr/page-adaf7bffff7a8527.js","/_next/static/chunks/app/(app)/inventory/page-a173a88d3bc1beeb.js","/_next/static/chunks/app/(app)/labels/page-f85ae0a0aca7a02a.js","/_next/static/chunks/app/(app)/layout-76831e120b0d4b46.js","/_next/static/chunks/app/(app)/logs/page-3bb6c86bfdeb4241.js","/_next/static/chunks/app/(app)/org/page-05fce8dc3265fc74.js","/_next/static/chunks/app/(app)/platform-activity/page-1ea798d47e62246f.js","/_next/static/chunks/app/(app)/platform-analytics/page-4cd4b7b8a24232e0.js","/_next/static/chunks/app/(app)/platform-companies/page-304b463addcdae12.js","/_next/static/chunks/app/(app)/platform-errors/page-954433c071de25ac.js","/_next/static/chunks/app/(app)/platform-finance/page-c485a9b0daad2683.js","/_next/static/chunks/app/(app)/platform-leads/page-37494ee53d496bc8.js","/_next/static/chunks/app/(app)/platform-plans/page-d857652037091ffe.js","/_next/static/chunks/app/(app)/platform-registrations/page-a4154683148a9a74.js","/_next/static/chunks/app/(app)/platform-seo/page-3f0a8a27a4a858b2.js","/_next/static/chunks/app/(app)/platform-subscriptions/page-8c0d04cd1ac4f43b.js","/_next/static/chunks/app/(app)/platform-team/member/page-3019283cff6d019b.js","/_next/static/chunks/app/(app)/platform-team/page-1eeb10c14e866f1d.js","/_next/static/chunks/app/(app)/platform/page-e3a732949f60f8ae.js","/_next/static/chunks/app/(app)/purchasing/page-4746ffd8c551a76f.js","/_next/static/chunks/app/(app)/reports/page-73ad242806ed5171.js","/_next/static/chunks/app/(app)/returns/page-83a3cd17232d3d64.js","/_next/static/chunks/app/(app)/sales/page-6ed4862c470796c1.js","/_next/static/chunks/app/(app)/settings/page-34f97031e58520d9.js","/_next/static/chunks/app/(app)/subscription/page-01308882e21cd640.js","/_next/static/chunks/app/(app)/supplier-records/page-278844660ad1ebaf.js","/_next/static/chunks/app/(app)/users/detail/page-0027cd6bdd1c1210.js","/_next/static/chunks/app/(app)/users/page-24b6473b87f639f2.js","/_next/static/chunks/app/(app)/web-orders/page-bf4b598895ca9101.js","/_next/static/chunks/app/(app)/website/page-1ae2c8bbd1eb9d66.js","/_next/static/chunks/app/(marketing)/compare/[slug]/page-4cc173930b193716.js","/_next/static/chunks/app/(marketing)/en/compare/[slug]/page-64761d44069ffa8c.js","/_next/static/chunks/app/(marketing)/en/guides/[slug]/page-fc170bff99809c7d.js","/_next/static/chunks/app/(marketing)/en/guides/page-1eea59b5b8a4fb9c.js","/_next/static/chunks/app/(marketing)/en/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/en/page-f40aef91fd5040e7.js","/_next/static/chunks/app/(marketing)/en/pricing/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/en/pricing/page-51a70e57580163bb.js","/_next/static/chunks/app/(marketing)/en/product/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/en/product/page-d5ae8aec5b33c35a.js","/_next/static/chunks/app/(marketing)/en/register/hosting/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/en/register/hosting/page-ef2643d2b81f6b7a.js","/_next/static/chunks/app/(marketing)/en/register/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/en/register/page-dda2d00464f8448d.js","/_next/static/chunks/app/(marketing)/en/solutions/[slug]/page-6eaae3249506d35a.js","/_next/static/chunks/app/(marketing)/en/solutions/page-b4c109b51baddc86.js","/_next/static/chunks/app/(marketing)/guides/[slug]/page-caa091e291fa2353.js","/_next/static/chunks/app/(marketing)/guides/page-988e9a669577f176.js","/_next/static/chunks/app/(marketing)/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/page-60ced59f7288311c.js","/_next/static/chunks/app/(marketing)/pricing/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/pricing/page-8b58c04469c72113.js","/_next/static/chunks/app/(marketing)/product/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/product/page-45f408284667e49c.js","/_next/static/chunks/app/(marketing)/register/hosting/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/register/hosting/page-14f662e70fc005ce.js","/_next/static/chunks/app/(marketing)/register/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/register/page-73fcdf8fd383330c.js","/_next/static/chunks/app/(marketing)/solutions/[slug]/page-7dad3d772fcd73f8.js","/_next/static/chunks/app/(marketing)/solutions/page-661789d2f7135cf9.js","/_next/static/chunks/app/_not-found/page-93f5ecd9b5a1b8d5.js","/_next/static/chunks/app/activate-owner/layout-163c837417bd2db7.js","/_next/static/chunks/app/activate-owner/page-c90c929e580cd6b9.js","/_next/static/chunks/app/forgot-password/layout-163c837417bd2db7.js","/_next/static/chunks/app/forgot-password/page-3acdfb0c414fbe23.js","/_next/static/chunks/app/layout-a03568667ed015e7.js","/_next/static/chunks/app/login/layout-163c837417bd2db7.js","/_next/static/chunks/app/login/page-934e0c06bcb845d3.js","/_next/static/chunks/app/reset-password/layout-163c837417bd2db7.js","/_next/static/chunks/app/reset-password/page-3c306aeddc9102ab.js","/_next/static/chunks/app/robots.txt/route-163c837417bd2db7.js","/_next/static/chunks/app/sitemap.xml/route-163c837417bd2db7.js","/_next/static/chunks/framework-ac871cde7d705c3a.js","/_next/static/chunks/main-61969269e7b3dad5.js","/_next/static/chunks/main-app-d3c2614b980cfab3.js","/_next/static/chunks/pages/_app-c0e3f7ff6ef43cb0.js","/_next/static/chunks/pages/_error-6bf3d2bf6fe2d033.js","/_next/static/chunks/polyfills-42372ed130431b0a.js","/_next/static/chunks/webpack-2e36f40915576872.js","/_next/static/css/3733534ea819bc6d.css","/_next/static/media/011e180705008d6f-s.woff2","/_next/static/media/19cfc7226ec3afaa-s.woff2","/_next/static/media/1ebb550cd0a67fc6-s.p.woff2","/_next/static/media/21350d82a1f187e9-s.woff2","/_next/static/media/3dc379dc9b5dec12-s.p.woff2","/_next/static/media/58f386aa6b1a2a92-s.woff2","/_next/static/media/63a79a6cf340c5d2-s.p.woff2","/_next/static/media/7ba5fb2a8c88521c-s.woff2","/_next/static/media/8e9860b6e62d6359-s.woff2","/_next/static/media/92eeb95d069020cc-s.woff2","/_next/static/media/98e207f02528a563-s.p.woff2","/_next/static/media/99dcf268bda04fe5-s.woff2","/_next/static/media/ba9851c3c22cd980-s.woff2","/_next/static/media/c5f10e9e72d35c52-s.woff2","/_next/static/media/c5fe6dc8356a8c31-s.woff2","/_next/static/media/ce401babc0566bc1-s.woff2","/_next/static/media/d29838c109ef09b4-s.woff2","/_next/static/media/d3ebbfd689654d3a-s.p.woff2","/_next/static/media/dd994fbf464986f0-s.p.woff2","/_next/static/media/df0a9ae256c0569c-s.woff2","/_next/static/media/e40af3453d7c920a-s.woff2","/_next/static/media/e4af272ccee01ff0-s.p.woff2","/_next/static/media/e97026df054cf2a3-s.woff2","/_next/static/media/ef4d5661765d0e49-s.woff2","/_next/static/media/f15f45d13243c643-s.woff2","/icons/apple-touch-icon.png","/icons/icon-192.png","/icons/icon-512.png","/icons/icon-maskable-192.png","/icons/icon-maskable-512.png","/manifest.webmanifest"];
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
