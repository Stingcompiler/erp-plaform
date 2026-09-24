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
const BUILD = "jmz0kbSUcX_zu8mUKQOre";
const CACHE = `vezano-shell-${BUILD}`;
// Every screen of the app, so the person lands on the page they asked for
// with no network — never on a different one. Filled in at build time from
// the export; the list below is the floor the PWA manifest relies on.
const PRECACHE_PAGES = ["/", "/login/", "/dashboard/", "/sales/", "/inventory/", "/returns/"];
const PRECACHE_APP_PAGES = ["/activate-owner/","/crm/","/customer-records/","/dashboard/","/debts/","/finance/","/forgot-password/","/hr/","/inventory/","/labels/","/login/","/logs/","/org/","/platform-activity/","/platform-analytics/","/platform-companies/","/platform-errors/","/platform-finance/","/platform-leads/","/platform-plans/","/platform-registrations/","/platform-seo/","/platform-subscriptions/","/platform-team/","/platform-team/member/","/platform/","/purchasing/","/reports/","/reset-password/","/returns/","/sales/","/settings/","/subscription/","/supplier-records/","/users/","/users/detail/","/web-orders/","/website/"];
// Every hashed chunk, stylesheet and font of this build, plus the manifest
// and icons — filled in at build time from the export.
const PRECACHE_ASSETS = ["/_next/static/chunks/1391-0b93ee9d9f7c21e5.js","/_next/static/chunks/1801-7e61d58fc5519497.js","/_next/static/chunks/2127-dc6abf93775fe235.js","/_next/static/chunks/2220-28c95603ac346713.js","/_next/static/chunks/2395-2840df6565c7c063.js","/_next/static/chunks/2901-401f1a92695f4c98.js","/_next/static/chunks/3106-dc54beff2352305c.js","/_next/static/chunks/3415-5f7f0b13d47da095.js","/_next/static/chunks/3902-22f25e9dffa5bfea.js","/_next/static/chunks/3995-193cf33b08e91925.js","/_next/static/chunks/40b91c18-03576e02c01e0947.js","/_next/static/chunks/4200-086e4dd05ced843c.js","/_next/static/chunks/4265-4b9c0eb9f5971919.js","/_next/static/chunks/4473-acbbb3b1e30980db.js","/_next/static/chunks/4686-0d5bf7045dd075f7.js","/_next/static/chunks/4838-602fb653293e1435.js","/_next/static/chunks/4878-df35a09aad37a893.js","/_next/static/chunks/5127-96cd5235f2a3ba1c.js","/_next/static/chunks/5270-bbb95e5f3a6afaf1.js","/_next/static/chunks/5405.6b9d8c3845e2492a.js","/_next/static/chunks/5410-087bc64c21c04d17.js","/_next/static/chunks/5471-6bbb878e528f48a8.js","/_next/static/chunks/5850-bba505c71ea8b9e4.js","/_next/static/chunks/6472-6ce7a3cce4a6401b.js","/_next/static/chunks/6702-5a33da0ccd8afcac.js","/_next/static/chunks/7655-eff8438d163b666c.js","/_next/static/chunks/7670-1056d442efeb12ab.js","/_next/static/chunks/7769-313f6fad97c64c58.js","/_next/static/chunks/8117-7b8cad2342bec1fa.js","/_next/static/chunks/8430-f929184bb61c728a.js","/_next/static/chunks/app/(app)/crm/page-75f110c599f80562.js","/_next/static/chunks/app/(app)/customer-records/page-7e32a042ababd08b.js","/_next/static/chunks/app/(app)/dashboard/page-e0905d417aa10299.js","/_next/static/chunks/app/(app)/debts/page-3a767c7b3319ae09.js","/_next/static/chunks/app/(app)/finance/page-747414f0d43f4e95.js","/_next/static/chunks/app/(app)/hr/page-a912ab0cba0e2ce7.js","/_next/static/chunks/app/(app)/inventory/page-fd312dba1b6660fc.js","/_next/static/chunks/app/(app)/labels/page-e4fee46c5d3afe31.js","/_next/static/chunks/app/(app)/layout-244f1e01b53359a2.js","/_next/static/chunks/app/(app)/logs/page-e94f0efce5fa5483.js","/_next/static/chunks/app/(app)/org/page-eac0b387faa8793b.js","/_next/static/chunks/app/(app)/platform-activity/page-6a3727b186bfdfa2.js","/_next/static/chunks/app/(app)/platform-analytics/page-0734690f7fdea513.js","/_next/static/chunks/app/(app)/platform-companies/page-708175a081313617.js","/_next/static/chunks/app/(app)/platform-errors/page-8ff2f53514564241.js","/_next/static/chunks/app/(app)/platform-finance/page-d9111f91db92b79a.js","/_next/static/chunks/app/(app)/platform-leads/page-70a669233fa6f5ec.js","/_next/static/chunks/app/(app)/platform-plans/page-6a8f1be23175f1a6.js","/_next/static/chunks/app/(app)/platform-registrations/page-2b1fdca071ced44b.js","/_next/static/chunks/app/(app)/platform-seo/page-a52bd51294e4ad78.js","/_next/static/chunks/app/(app)/platform-subscriptions/page-f2e21c63c1257f5e.js","/_next/static/chunks/app/(app)/platform-team/member/page-59de024fb254d93c.js","/_next/static/chunks/app/(app)/platform-team/page-52c23f4cfa6282a9.js","/_next/static/chunks/app/(app)/platform/page-839c7414a080d28b.js","/_next/static/chunks/app/(app)/purchasing/page-3103ae5817e51184.js","/_next/static/chunks/app/(app)/reports/page-966e0e23acb1f26b.js","/_next/static/chunks/app/(app)/returns/page-d0601b3cddeee1ac.js","/_next/static/chunks/app/(app)/sales/page-108ab3900d923a47.js","/_next/static/chunks/app/(app)/settings/page-0d9912fe81a01cea.js","/_next/static/chunks/app/(app)/subscription/page-fa07cc210c0fab61.js","/_next/static/chunks/app/(app)/supplier-records/page-6c0cbba78653b01b.js","/_next/static/chunks/app/(app)/users/detail/page-e90e70eb8da40f63.js","/_next/static/chunks/app/(app)/users/page-a9b39b99d8032dab.js","/_next/static/chunks/app/(app)/web-orders/page-947ab47c7b7c50ee.js","/_next/static/chunks/app/(app)/website/page-dc787ba3ffb78f29.js","/_next/static/chunks/app/(marketing)/compare/[slug]/page-9f9dbd8ee80d842e.js","/_next/static/chunks/app/(marketing)/en/compare/[slug]/page-0d82b3b95533b013.js","/_next/static/chunks/app/(marketing)/en/guides/[slug]/page-07c2298dba03d5ed.js","/_next/static/chunks/app/(marketing)/en/guides/page-374c6190a3a0f98f.js","/_next/static/chunks/app/(marketing)/en/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/en/page-d50876b9b8bb32f3.js","/_next/static/chunks/app/(marketing)/en/pricing/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/en/pricing/page-f54dec9319c41a71.js","/_next/static/chunks/app/(marketing)/en/product/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/en/product/page-6299efb73ec6c8bd.js","/_next/static/chunks/app/(marketing)/en/register/hosting/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/en/register/hosting/page-3e6cc2452b81a663.js","/_next/static/chunks/app/(marketing)/en/register/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/en/register/page-e17ece2970f2e695.js","/_next/static/chunks/app/(marketing)/en/solutions/[slug]/page-30834ceb5359e216.js","/_next/static/chunks/app/(marketing)/en/solutions/page-605e69d018ea7069.js","/_next/static/chunks/app/(marketing)/guides/[slug]/page-3d5e57e4cd7b776b.js","/_next/static/chunks/app/(marketing)/guides/page-11cc65319207480c.js","/_next/static/chunks/app/(marketing)/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/page-345a589b2edb48bf.js","/_next/static/chunks/app/(marketing)/pricing/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/pricing/page-15a9be4f53437eee.js","/_next/static/chunks/app/(marketing)/product/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/product/page-d5ac1765bc912f1d.js","/_next/static/chunks/app/(marketing)/register/hosting/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/register/hosting/page-00799b532bd21764.js","/_next/static/chunks/app/(marketing)/register/layout-163c837417bd2db7.js","/_next/static/chunks/app/(marketing)/register/page-7e9c550b0e081671.js","/_next/static/chunks/app/(marketing)/solutions/[slug]/page-b5741c0125b5af84.js","/_next/static/chunks/app/(marketing)/solutions/page-206b94efc07ea3d2.js","/_next/static/chunks/app/_not-found/page-93f5ecd9b5a1b8d5.js","/_next/static/chunks/app/activate-owner/layout-163c837417bd2db7.js","/_next/static/chunks/app/activate-owner/page-7a57b7183b78d96c.js","/_next/static/chunks/app/forgot-password/layout-163c837417bd2db7.js","/_next/static/chunks/app/forgot-password/page-349c55523489c465.js","/_next/static/chunks/app/layout-51b35b7c670c814a.js","/_next/static/chunks/app/login/layout-163c837417bd2db7.js","/_next/static/chunks/app/login/page-e8e7a28db83fa26c.js","/_next/static/chunks/app/reset-password/layout-163c837417bd2db7.js","/_next/static/chunks/app/reset-password/page-37067316aaccceef.js","/_next/static/chunks/app/robots.txt/route-163c837417bd2db7.js","/_next/static/chunks/app/sitemap.xml/route-163c837417bd2db7.js","/_next/static/chunks/framework-ac871cde7d705c3a.js","/_next/static/chunks/main-61969269e7b3dad5.js","/_next/static/chunks/main-app-d3c2614b980cfab3.js","/_next/static/chunks/pages/_app-c0e3f7ff6ef43cb0.js","/_next/static/chunks/pages/_error-6bf3d2bf6fe2d033.js","/_next/static/chunks/polyfills-42372ed130431b0a.js","/_next/static/chunks/webpack-076a034402f93b3f.js","/_next/static/css/7d876e664442c41a.css","/_next/static/jmz0kbSUcX_zu8mUKQOre/_buildManifest.js","/_next/static/jmz0kbSUcX_zu8mUKQOre/_ssgManifest.js","/_next/static/media/011e180705008d6f-s.woff2","/_next/static/media/01f0c602c274ea55-s.woff2","/_next/static/media/19cfc7226ec3afaa-s.woff2","/_next/static/media/1ebb550cd0a67fc6-s.p.woff2","/_next/static/media/21350d82a1f187e9-s.woff2","/_next/static/media/350b852752f8489d-s.p.woff2","/_next/static/media/3dc379dc9b5dec12-s.p.woff2","/_next/static/media/58f386aa6b1a2a92-s.woff2","/_next/static/media/5ec84f17416dda4d-s.woff2","/_next/static/media/63a79a6cf340c5d2-s.p.woff2","/_next/static/media/7ba5fb2a8c88521c-s.woff2","/_next/static/media/8e9860b6e62d6359-s.woff2","/_next/static/media/92eeb95d069020cc-s.woff2","/_next/static/media/98e207f02528a563-s.p.woff2","/_next/static/media/99dcf268bda04fe5-s.woff2","/_next/static/media/ba9851c3c22cd980-s.woff2","/_next/static/media/c5f10e9e72d35c52-s.woff2","/_next/static/media/c5fe6dc8356a8c31-s.woff2","/_next/static/media/ce401babc0566bc1-s.woff2","/_next/static/media/d29838c109ef09b4-s.woff2","/_next/static/media/d3ebbfd689654d3a-s.p.woff2","/_next/static/media/dd994fbf464986f0-s.p.woff2","/_next/static/media/df0a9ae256c0569c-s.woff2","/_next/static/media/e40af3453d7c920a-s.woff2","/_next/static/media/e4af272ccee01ff0-s.p.woff2","/_next/static/media/e97026df054cf2a3-s.woff2","/_next/static/media/ef4d5661765d0e49-s.woff2","/_next/static/media/f15f45d13243c643-s.woff2","/icons/apple-touch-icon.png","/icons/icon-192.png","/icons/icon-512.png","/icons/icon-maskable-192.png","/icons/icon-maskable-512.png","/manifest.webmanifest"];
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
