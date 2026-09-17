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
const BUILD = "d9c25WLxq79P1J6KKactX";
const CACHE = `vezano-shell-${BUILD}`;
// Routes a cashier needs reachable with no network at all.
const PRECACHE_PAGES = ["/", "/login/", "/dashboard/", "/sales/", "/inventory/", "/returns/"];
// Every hashed chunk, stylesheet and font of this build, plus the manifest
// and icons — filled in at build time from the export.
const PRECACHE_ASSETS = ["/_next/static/chunks/1228-bef48ccf9ad95171.js","/_next/static/chunks/1255-98c7bc7e87a73c35.js","/_next/static/chunks/1360-a63624d9d55392e6.js","/_next/static/chunks/1597-6ebae43328043d95.js","/_next/static/chunks/2688-b82b91f2fd89c5fa.js","/_next/static/chunks/27-750158b69f30526a.js","/_next/static/chunks/3302-158cbb30bdb59dd3.js","/_next/static/chunks/3607-4b6eeb23f6db2bbc.js","/_next/static/chunks/4050-47a3c8ecaec76a9b.js","/_next/static/chunks/475-a5890e239a958347.js","/_next/static/chunks/4796-f7c1333c308d8305.js","/_next/static/chunks/4bd1b696-f785427dddbba9fb.js","/_next/static/chunks/536-f1c619515158ddaa.js","/_next/static/chunks/5596-1fd9a014411a8d80.js","/_next/static/chunks/6067-75b1d13502a352cc.js","/_next/static/chunks/6535-6ab0491b4236f879.js","/_next/static/chunks/7289-982c8cae7aa1b844.js","/_next/static/chunks/8838-69fd676cf0e7ddcc.js","/_next/static/chunks/8944-e80b89e15308354c.js","/_next/static/chunks/9475-f5786c9b976d2b53.js","/_next/static/chunks/app/(app)/crm/page-c357341133762ffc.js","/_next/static/chunks/app/(app)/customer-records/page-485d1c543976ba9f.js","/_next/static/chunks/app/(app)/dashboard/page-a0b71a1a7eefc7bf.js","/_next/static/chunks/app/(app)/debts/page-bd4d967a5b0f2b29.js","/_next/static/chunks/app/(app)/finance/page-3a8dc5744afce8f1.js","/_next/static/chunks/app/(app)/hr/page-e374fa227225ed42.js","/_next/static/chunks/app/(app)/inventory/page-0d31a39c146ce66b.js","/_next/static/chunks/app/(app)/labels/page-0011d26b6b77018f.js","/_next/static/chunks/app/(app)/layout-9559c8ad85d88f66.js","/_next/static/chunks/app/(app)/logs/page-1be41d0a962631df.js","/_next/static/chunks/app/(app)/org/page-797f891455d1ba32.js","/_next/static/chunks/app/(app)/platform-activity/page-14f972d8d5a6efea.js","/_next/static/chunks/app/(app)/platform-leads/page-dafb98136625f24c.js","/_next/static/chunks/app/(app)/platform-plans/page-5853a7a2dfae2105.js","/_next/static/chunks/app/(app)/platform-registrations/page-1c48d297e610871e.js","/_next/static/chunks/app/(app)/platform-seo/page-92205037d1e00dfe.js","/_next/static/chunks/app/(app)/platform-subscriptions/page-91541658418d0452.js","/_next/static/chunks/app/(app)/platform-team/member/page-d0a6349600f0599e.js","/_next/static/chunks/app/(app)/platform-team/page-13cc661cda4ed97d.js","/_next/static/chunks/app/(app)/platform/page-5f7ae25c913c6d23.js","/_next/static/chunks/app/(app)/purchasing/page-de5c4f84e0fe6439.js","/_next/static/chunks/app/(app)/reports/page-547ba235a2f9a927.js","/_next/static/chunks/app/(app)/returns/page-a00d3427cf302abc.js","/_next/static/chunks/app/(app)/sales/page-a2bf189da903be1c.js","/_next/static/chunks/app/(app)/settings/page-eddde929c3c8cf2b.js","/_next/static/chunks/app/(app)/subscription/page-af6a5a082c096818.js","/_next/static/chunks/app/(app)/supplier-records/page-5327614a1d8cb052.js","/_next/static/chunks/app/(app)/users/detail/page-17dc4833a5c15f59.js","/_next/static/chunks/app/(app)/users/page-8f6e58b0be1442b6.js","/_next/static/chunks/app/(app)/website/page-5df02387e1fbfd5c.js","/_next/static/chunks/app/(marketing)/compare/[slug]/page-30ffcb9b0a0b4f2b.js","/_next/static/chunks/app/(marketing)/en/compare/[slug]/page-10f3735d46380126.js","/_next/static/chunks/app/(marketing)/en/guides/[slug]/page-fdddaa9c10a8b383.js","/_next/static/chunks/app/(marketing)/en/guides/page-8ca5386b5e577324.js","/_next/static/chunks/app/(marketing)/en/layout-878b72b5c7f971a0.js","/_next/static/chunks/app/(marketing)/en/page-8ac87e2adeea9288.js","/_next/static/chunks/app/(marketing)/en/pricing/layout-878b72b5c7f971a0.js","/_next/static/chunks/app/(marketing)/en/pricing/page-12d2bf30ffaa31fa.js","/_next/static/chunks/app/(marketing)/en/product/layout-878b72b5c7f971a0.js","/_next/static/chunks/app/(marketing)/en/product/page-5209e10eb4f82d26.js","/_next/static/chunks/app/(marketing)/en/register/layout-878b72b5c7f971a0.js","/_next/static/chunks/app/(marketing)/en/register/page-d4fda3c38f2990bc.js","/_next/static/chunks/app/(marketing)/en/solutions/[slug]/page-d9b1f30c120b7546.js","/_next/static/chunks/app/(marketing)/en/solutions/page-2e6079047a9af1b9.js","/_next/static/chunks/app/(marketing)/guides/[slug]/page-a66d09f76cafed9b.js","/_next/static/chunks/app/(marketing)/guides/page-6164b4e942cda426.js","/_next/static/chunks/app/(marketing)/layout-878b72b5c7f971a0.js","/_next/static/chunks/app/(marketing)/page-f1a7b5073be65765.js","/_next/static/chunks/app/(marketing)/pricing/layout-878b72b5c7f971a0.js","/_next/static/chunks/app/(marketing)/pricing/page-bcfc7fffbeb3a67a.js","/_next/static/chunks/app/(marketing)/product/layout-878b72b5c7f971a0.js","/_next/static/chunks/app/(marketing)/product/page-5fc0cf3b8e96215a.js","/_next/static/chunks/app/(marketing)/register/layout-878b72b5c7f971a0.js","/_next/static/chunks/app/(marketing)/register/page-a79833f35ade4533.js","/_next/static/chunks/app/(marketing)/solutions/[slug]/page-27e17213f33f6954.js","/_next/static/chunks/app/(marketing)/solutions/page-462f36a0fa9759ac.js","/_next/static/chunks/app/_not-found/page-9a815cd54e226669.js","/_next/static/chunks/app/activate-owner/layout-878b72b5c7f971a0.js","/_next/static/chunks/app/activate-owner/page-4eae9348ab6a7219.js","/_next/static/chunks/app/layout-80704be3515898a8.js","/_next/static/chunks/app/login/layout-878b72b5c7f971a0.js","/_next/static/chunks/app/login/page-1f41befd33d87b7f.js","/_next/static/chunks/app/robots.txt/route-878b72b5c7f971a0.js","/_next/static/chunks/app/sitemap.xml/route-878b72b5c7f971a0.js","/_next/static/chunks/framework-67e87833b9140bb8.js","/_next/static/chunks/main-5d1e69c8bcbbac27.js","/_next/static/chunks/main-app-6c415923d9b40f4e.js","/_next/static/chunks/pages/_app-6c8c2371b16a04b8.js","/_next/static/chunks/pages/_error-94812ad32cad7365.js","/_next/static/chunks/polyfills-42372ed130431b0a.js","/_next/static/chunks/webpack-b94a8e12653a79f9.js","/_next/static/css/af2ef66925d8edb8.css","/_next/static/d9c25WLxq79P1J6KKactX/_buildManifest.js","/_next/static/d9c25WLxq79P1J6KKactX/_ssgManifest.js","/_next/static/media/011e180705008d6f-s.woff2","/_next/static/media/01f0c602c274ea55-s.woff2","/_next/static/media/19cfc7226ec3afaa-s.woff2","/_next/static/media/1ebb550cd0a67fc6-s.p.woff2","/_next/static/media/21350d82a1f187e9-s.woff2","/_next/static/media/350b852752f8489d-s.p.woff2","/_next/static/media/3dc379dc9b5dec12-s.p.woff2","/_next/static/media/58f386aa6b1a2a92-s.woff2","/_next/static/media/5ec84f17416dda4d-s.woff2","/_next/static/media/63a79a6cf340c5d2-s.p.woff2","/_next/static/media/7ba5fb2a8c88521c-s.woff2","/_next/static/media/8e9860b6e62d6359-s.woff2","/_next/static/media/92eeb95d069020cc-s.woff2","/_next/static/media/98e207f02528a563-s.p.woff2","/_next/static/media/99dcf268bda04fe5-s.woff2","/_next/static/media/ba9851c3c22cd980-s.woff2","/_next/static/media/c5f10e9e72d35c52-s.woff2","/_next/static/media/c5fe6dc8356a8c31-s.woff2","/_next/static/media/ce401babc0566bc1-s.woff2","/_next/static/media/d29838c109ef09b4-s.woff2","/_next/static/media/d3ebbfd689654d3a-s.p.woff2","/_next/static/media/dd994fbf464986f0-s.p.woff2","/_next/static/media/df0a9ae256c0569c-s.woff2","/_next/static/media/e40af3453d7c920a-s.woff2","/_next/static/media/e4af272ccee01ff0-s.p.woff2","/_next/static/media/e97026df054cf2a3-s.woff2","/_next/static/media/ef4d5661765d0e49-s.woff2","/_next/static/media/f15f45d13243c643-s.woff2","/icons/apple-touch-icon.png","/icons/icon-192.png","/icons/icon-512.png","/icons/icon-maskable-192.png","/icons/icon-maskable-512.png","/manifest.webmanifest"];
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
