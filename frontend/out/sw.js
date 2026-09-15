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
const BUILD = "96CztX_zdpaz1rxXlAS3u";
const CACHE = `vezano-shell-${BUILD}`;
// Routes a cashier needs reachable with no network at all.
const PRECACHE_PAGES = ["/", "/login/", "/dashboard/", "/sales/", "/inventory/", "/returns/"];
// Every hashed chunk, stylesheet and font of this build, plus the manifest
// and icons — filled in at build time from the export.
const PRECACHE_ASSETS = ["/_next/static/96CztX_zdpaz1rxXlAS3u/_buildManifest.js","/_next/static/96CztX_zdpaz1rxXlAS3u/_ssgManifest.js","/_next/static/chunks/1103-ba000b9214c64ae0.js","/_next/static/chunks/1228-bef48ccf9ad95171.js","/_next/static/chunks/1255-98c7bc7e87a73c35.js","/_next/static/chunks/177-d4f64a819ccd4d20.js","/_next/static/chunks/2870-dd7a1a8f9d59f36b.js","/_next/static/chunks/3327-023132ce4f1f40d8.js","/_next/static/chunks/3607-c5174feb3d24e120.js","/_next/static/chunks/4050-4d0a021d40ccfea3.js","/_next/static/chunks/4496-f5f4dfe43f98efd2.js","/_next/static/chunks/475-01436742ffaa7171.js","/_next/static/chunks/4796-f7c1333c308d8305.js","/_next/static/chunks/4bd1b696-f785427dddbba9fb.js","/_next/static/chunks/8944-9062e1bb32d02827.js","/_next/static/chunks/9301-b273dad43e4c5e99.js","/_next/static/chunks/app/(app)/crm/page-dc4855a5d3c894f8.js","/_next/static/chunks/app/(app)/customer-records/page-d76ad3fef64bf611.js","/_next/static/chunks/app/(app)/dashboard/page-8231fece79176fc5.js","/_next/static/chunks/app/(app)/debts/page-6225a702948271bb.js","/_next/static/chunks/app/(app)/finance/page-6aa36d3087aa87ad.js","/_next/static/chunks/app/(app)/hr/page-e8c5d2297172c5f7.js","/_next/static/chunks/app/(app)/inventory/page-f82b4db07cbf1735.js","/_next/static/chunks/app/(app)/labels/page-75118a84b62f8139.js","/_next/static/chunks/app/(app)/layout-0ae03df77554a2d8.js","/_next/static/chunks/app/(app)/logs/page-ba4ed3ec905ed804.js","/_next/static/chunks/app/(app)/org/page-861b23e82109d7be.js","/_next/static/chunks/app/(app)/platform-leads/page-63a6ec489678b542.js","/_next/static/chunks/app/(app)/platform-plans/page-2db322d6962db655.js","/_next/static/chunks/app/(app)/platform-registrations/page-854eb0b8829dd48b.js","/_next/static/chunks/app/(app)/platform-subscriptions/page-692880dac372b74c.js","/_next/static/chunks/app/(app)/platform-team/page-5ea91589fb293f15.js","/_next/static/chunks/app/(app)/platform/page-cb8baf77e26abf01.js","/_next/static/chunks/app/(app)/purchasing/page-f072a84d321dc5af.js","/_next/static/chunks/app/(app)/reports/page-7e3506a3aec91a86.js","/_next/static/chunks/app/(app)/returns/page-304b06ac6e910023.js","/_next/static/chunks/app/(app)/sales/page-77043e6a445a5baa.js","/_next/static/chunks/app/(app)/settings/page-038752a3fe8cd748.js","/_next/static/chunks/app/(app)/subscription/page-99d2413aad8493fd.js","/_next/static/chunks/app/(app)/supplier-records/page-2644177db5d87a3b.js","/_next/static/chunks/app/(app)/users/page-3df0b444b2db38f6.js","/_next/static/chunks/app/(app)/website/page-824345135b46ae1c.js","/_next/static/chunks/app/(marketing)/layout-8a4c15c6a0800bdf.js","/_next/static/chunks/app/(marketing)/page-1c8e6fe8a07e8b5c.js","/_next/static/chunks/app/(marketing)/pricing/layout-8a4c15c6a0800bdf.js","/_next/static/chunks/app/(marketing)/pricing/page-835f896e7bc6d2df.js","/_next/static/chunks/app/(marketing)/product/layout-8a4c15c6a0800bdf.js","/_next/static/chunks/app/(marketing)/product/page-6c0886bd28bc0687.js","/_next/static/chunks/app/(marketing)/register/layout-8a4c15c6a0800bdf.js","/_next/static/chunks/app/(marketing)/register/page-c61b68be06c00168.js","/_next/static/chunks/app/_not-found/page-9a815cd54e226669.js","/_next/static/chunks/app/activate-owner/layout-8a4c15c6a0800bdf.js","/_next/static/chunks/app/activate-owner/page-fbb0b9587424963a.js","/_next/static/chunks/app/layout-981c016186c6b666.js","/_next/static/chunks/app/login/layout-8a4c15c6a0800bdf.js","/_next/static/chunks/app/login/page-7bd3e3fdf3ea3176.js","/_next/static/chunks/app/robots.txt/route-8a4c15c6a0800bdf.js","/_next/static/chunks/app/sitemap.xml/route-8a4c15c6a0800bdf.js","/_next/static/chunks/framework-67e87833b9140bb8.js","/_next/static/chunks/main-5d1e69c8bcbbac27.js","/_next/static/chunks/main-app-6c415923d9b40f4e.js","/_next/static/chunks/pages/_app-6c8c2371b16a04b8.js","/_next/static/chunks/pages/_error-94812ad32cad7365.js","/_next/static/chunks/polyfills-42372ed130431b0a.js","/_next/static/chunks/webpack-b94a8e12653a79f9.js","/_next/static/css/c8266ef6d5e5cbe9.css","/_next/static/media/011e180705008d6f-s.woff2","/_next/static/media/01f0c602c274ea55-s.woff2","/_next/static/media/19cfc7226ec3afaa-s.woff2","/_next/static/media/1ebb550cd0a67fc6-s.p.woff2","/_next/static/media/21350d82a1f187e9-s.woff2","/_next/static/media/350b852752f8489d-s.p.woff2","/_next/static/media/3dc379dc9b5dec12-s.p.woff2","/_next/static/media/58f386aa6b1a2a92-s.woff2","/_next/static/media/5ec84f17416dda4d-s.woff2","/_next/static/media/63a79a6cf340c5d2-s.p.woff2","/_next/static/media/7ba5fb2a8c88521c-s.woff2","/_next/static/media/8e9860b6e62d6359-s.woff2","/_next/static/media/92eeb95d069020cc-s.woff2","/_next/static/media/98e207f02528a563-s.p.woff2","/_next/static/media/99dcf268bda04fe5-s.woff2","/_next/static/media/ba9851c3c22cd980-s.woff2","/_next/static/media/c5f10e9e72d35c52-s.woff2","/_next/static/media/c5fe6dc8356a8c31-s.woff2","/_next/static/media/ce401babc0566bc1-s.woff2","/_next/static/media/d29838c109ef09b4-s.woff2","/_next/static/media/d3ebbfd689654d3a-s.p.woff2","/_next/static/media/dd994fbf464986f0-s.p.woff2","/_next/static/media/df0a9ae256c0569c-s.woff2","/_next/static/media/e40af3453d7c920a-s.woff2","/_next/static/media/e4af272ccee01ff0-s.p.woff2","/_next/static/media/e97026df054cf2a3-s.woff2","/_next/static/media/ef4d5661765d0e49-s.woff2","/_next/static/media/f15f45d13243c643-s.woff2","/icons/apple-touch-icon.png","/icons/icon-192.png","/icons/icon-512.png","/icons/icon-maskable-192.png","/icons/icon-maskable-512.png","/manifest.webmanifest"];
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
      cache.addAll([...PRECACHE_PAGES, ...PRECACHE_ASSETS].map((url) => new Request(url, { cache: "reload" }))),
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
    // Exact page first, then the same page with/without trailing slash, then
    // the POS as the most useful screen to land on with no network.
    const url = new URL(request.url);
    const variants = [url.pathname, url.pathname.replace(/\/?$/, "/"), "/sales/", "/dashboard/"];
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
