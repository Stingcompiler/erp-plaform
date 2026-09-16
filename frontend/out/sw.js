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
const BUILD = "aINNkiGcZMtOx-v2PsNt9";
const CACHE = `vezano-shell-${BUILD}`;
// Routes a cashier needs reachable with no network at all.
const PRECACHE_PAGES = ["/", "/login/", "/dashboard/", "/sales/", "/inventory/", "/returns/"];
// Every hashed chunk, stylesheet and font of this build, plus the manifest
// and icons — filled in at build time from the export.
const PRECACHE_ASSETS = ["/_next/static/aINNkiGcZMtOx-v2PsNt9/_buildManifest.js","/_next/static/aINNkiGcZMtOx-v2PsNt9/_ssgManifest.js","/_next/static/chunks/1004-0803462f0e988a28.js","/_next/static/chunks/1228-bef48ccf9ad95171.js","/_next/static/chunks/1255-98c7bc7e87a73c35.js","/_next/static/chunks/1741-fc08c58ebecf274f.js","/_next/static/chunks/2197-94240f0b691a1029.js","/_next/static/chunks/3302-cfe8da30f1c01f9f.js","/_next/static/chunks/3607-9f0c98dccefd544c.js","/_next/static/chunks/4050-5fe8f93e106db6e0.js","/_next/static/chunks/4295-bb0d9c12d1182085.js","/_next/static/chunks/475-01436742ffaa7171.js","/_next/static/chunks/4796-f7c1333c308d8305.js","/_next/static/chunks/4bd1b696-f785427dddbba9fb.js","/_next/static/chunks/5082-72ecd6a49efe53f6.js","/_next/static/chunks/5439-366ad5c53138cba7.js","/_next/static/chunks/546-6299dd62e17802ca.js","/_next/static/chunks/6919-07deeeb04f9fb538.js","/_next/static/chunks/7289-982c8cae7aa1b844.js","/_next/static/chunks/8299-de58a3bb014d3551.js","/_next/static/chunks/8944-9062e1bb32d02827.js","/_next/static/chunks/app/(app)/crm/page-c357341133762ffc.js","/_next/static/chunks/app/(app)/customer-records/page-485d1c543976ba9f.js","/_next/static/chunks/app/(app)/dashboard/page-d76c69f7f6d55473.js","/_next/static/chunks/app/(app)/debts/page-13e3fc1d188b982e.js","/_next/static/chunks/app/(app)/finance/page-3a8dc5744afce8f1.js","/_next/static/chunks/app/(app)/hr/page-e374fa227225ed42.js","/_next/static/chunks/app/(app)/inventory/page-7d7d4c2d1d4d8a3e.js","/_next/static/chunks/app/(app)/labels/page-976346daac8996b6.js","/_next/static/chunks/app/(app)/layout-e95d76a8c4e0c3ca.js","/_next/static/chunks/app/(app)/logs/page-1e38877383e844f4.js","/_next/static/chunks/app/(app)/org/page-eed354b4ccc5023e.js","/_next/static/chunks/app/(app)/platform-activity/page-eb6a7d80fea05e5a.js","/_next/static/chunks/app/(app)/platform-leads/page-86f96a6683b660e9.js","/_next/static/chunks/app/(app)/platform-plans/page-76c29a1f1fdf3c86.js","/_next/static/chunks/app/(app)/platform-registrations/page-e4b22ac0a9ab2c58.js","/_next/static/chunks/app/(app)/platform-subscriptions/page-396ad117fec4516c.js","/_next/static/chunks/app/(app)/platform-team/member/page-f095f02d560b6f9b.js","/_next/static/chunks/app/(app)/platform-team/page-c8e875959e0fd040.js","/_next/static/chunks/app/(app)/platform/page-15a84b02b305cd4e.js","/_next/static/chunks/app/(app)/purchasing/page-7156d6ed6046b22e.js","/_next/static/chunks/app/(app)/reports/page-4473825adb238590.js","/_next/static/chunks/app/(app)/returns/page-8aa6578e5a7ac49b.js","/_next/static/chunks/app/(app)/sales/page-e29a28531e96e179.js","/_next/static/chunks/app/(app)/settings/page-b2c8d564030a054c.js","/_next/static/chunks/app/(app)/subscription/page-f1b456f25d694d8c.js","/_next/static/chunks/app/(app)/supplier-records/page-5327614a1d8cb052.js","/_next/static/chunks/app/(app)/users/page-09f93c8f6104870a.js","/_next/static/chunks/app/(app)/website/page-a6782d62c59eb608.js","/_next/static/chunks/app/(marketing)/compare/[slug]/page-bfe24131daf2cd6f.js","/_next/static/chunks/app/(marketing)/en/compare/[slug]/page-7343e04454fb927a.js","/_next/static/chunks/app/(marketing)/en/guides/[slug]/page-b9d7a6380cb30368.js","/_next/static/chunks/app/(marketing)/en/guides/page-13a60692c1ef2f83.js","/_next/static/chunks/app/(marketing)/en/layout-878b72b5c7f971a0.js","/_next/static/chunks/app/(marketing)/en/page-55ace158aa61312d.js","/_next/static/chunks/app/(marketing)/en/pricing/layout-878b72b5c7f971a0.js","/_next/static/chunks/app/(marketing)/en/pricing/page-857dba8ec117cba0.js","/_next/static/chunks/app/(marketing)/en/product/layout-878b72b5c7f971a0.js","/_next/static/chunks/app/(marketing)/en/product/page-48119cb5938526a9.js","/_next/static/chunks/app/(marketing)/en/register/layout-878b72b5c7f971a0.js","/_next/static/chunks/app/(marketing)/en/register/page-e16e5dc31f19e6db.js","/_next/static/chunks/app/(marketing)/en/solutions/[slug]/page-d0e87d1c8b21a3c0.js","/_next/static/chunks/app/(marketing)/en/solutions/page-3665e5328bd151ac.js","/_next/static/chunks/app/(marketing)/guides/[slug]/page-f49535b24c35bcb0.js","/_next/static/chunks/app/(marketing)/guides/page-f1b4f4a14159b09a.js","/_next/static/chunks/app/(marketing)/layout-878b72b5c7f971a0.js","/_next/static/chunks/app/(marketing)/page-0fbf4523e4623fb3.js","/_next/static/chunks/app/(marketing)/pricing/layout-878b72b5c7f971a0.js","/_next/static/chunks/app/(marketing)/pricing/page-3522756d0d1105a0.js","/_next/static/chunks/app/(marketing)/product/layout-878b72b5c7f971a0.js","/_next/static/chunks/app/(marketing)/product/page-43778577f6ed75f1.js","/_next/static/chunks/app/(marketing)/register/layout-878b72b5c7f971a0.js","/_next/static/chunks/app/(marketing)/register/page-51c01d5de30c5bbb.js","/_next/static/chunks/app/(marketing)/solutions/[slug]/page-bf86cf5a76073d5f.js","/_next/static/chunks/app/(marketing)/solutions/page-35aaf4fa8170d9f3.js","/_next/static/chunks/app/_not-found/page-9a815cd54e226669.js","/_next/static/chunks/app/activate-owner/layout-878b72b5c7f971a0.js","/_next/static/chunks/app/activate-owner/page-9e0b1f4a58f17ada.js","/_next/static/chunks/app/layout-80704be3515898a8.js","/_next/static/chunks/app/login/layout-878b72b5c7f971a0.js","/_next/static/chunks/app/login/page-8c727badea4a1efe.js","/_next/static/chunks/app/robots.txt/route-878b72b5c7f971a0.js","/_next/static/chunks/app/sitemap.xml/route-878b72b5c7f971a0.js","/_next/static/chunks/framework-67e87833b9140bb8.js","/_next/static/chunks/main-5d1e69c8bcbbac27.js","/_next/static/chunks/main-app-6c415923d9b40f4e.js","/_next/static/chunks/pages/_app-6c8c2371b16a04b8.js","/_next/static/chunks/pages/_error-94812ad32cad7365.js","/_next/static/chunks/polyfills-42372ed130431b0a.js","/_next/static/chunks/webpack-b94a8e12653a79f9.js","/_next/static/css/c027bccb326d9589.css","/_next/static/media/011e180705008d6f-s.woff2","/_next/static/media/01f0c602c274ea55-s.woff2","/_next/static/media/19cfc7226ec3afaa-s.woff2","/_next/static/media/1ebb550cd0a67fc6-s.p.woff2","/_next/static/media/21350d82a1f187e9-s.woff2","/_next/static/media/350b852752f8489d-s.p.woff2","/_next/static/media/3dc379dc9b5dec12-s.p.woff2","/_next/static/media/58f386aa6b1a2a92-s.woff2","/_next/static/media/5ec84f17416dda4d-s.woff2","/_next/static/media/63a79a6cf340c5d2-s.p.woff2","/_next/static/media/7ba5fb2a8c88521c-s.woff2","/_next/static/media/8e9860b6e62d6359-s.woff2","/_next/static/media/92eeb95d069020cc-s.woff2","/_next/static/media/98e207f02528a563-s.p.woff2","/_next/static/media/99dcf268bda04fe5-s.woff2","/_next/static/media/ba9851c3c22cd980-s.woff2","/_next/static/media/c5f10e9e72d35c52-s.woff2","/_next/static/media/c5fe6dc8356a8c31-s.woff2","/_next/static/media/ce401babc0566bc1-s.woff2","/_next/static/media/d29838c109ef09b4-s.woff2","/_next/static/media/d3ebbfd689654d3a-s.p.woff2","/_next/static/media/dd994fbf464986f0-s.p.woff2","/_next/static/media/df0a9ae256c0569c-s.woff2","/_next/static/media/e40af3453d7c920a-s.woff2","/_next/static/media/e4af272ccee01ff0-s.p.woff2","/_next/static/media/e97026df054cf2a3-s.woff2","/_next/static/media/ef4d5661765d0e49-s.woff2","/_next/static/media/f15f45d13243c643-s.woff2","/icons/apple-touch-icon.png","/icons/icon-192.png","/icons/icon-512.png","/icons/icon-maskable-192.png","/icons/icon-maskable-512.png","/manifest.webmanifest"];
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
