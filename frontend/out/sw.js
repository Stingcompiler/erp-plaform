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
const BUILD = "h8ddmt1CWhfr71r4LNwRE";
const CACHE = `vezano-shell-${BUILD}`;
// Routes a cashier needs reachable with no network at all.
const PRECACHE_PAGES = ["/", "/login/", "/dashboard/", "/sales/", "/inventory/", "/returns/"];
// Every hashed chunk, stylesheet and font of this build, plus the manifest
// and icons — filled in at build time from the export.
const PRECACHE_ASSETS = ["/_next/static/chunks/1654-cfae15037ea63f50.js","/_next/static/chunks/2215-56cc1f43fefc93a7.js","/_next/static/chunks/2667-3f126880db19a705.js","/_next/static/chunks/3310-0c2e0aecbc41fc19.js","/_next/static/chunks/4008-b4be416bf29756e4.js","/_next/static/chunks/4868-2642b564631c8d0c.js","/_next/static/chunks/5039-c12e74b195b00dfa.js","/_next/static/chunks/5084-d926eb03d1f330d6.js","/_next/static/chunks/5141-bbbc731cd11b7ae7.js","/_next/static/chunks/5306-392f08460957c2b9.js","/_next/static/chunks/5462-c897333e07268651.js","/_next/static/chunks/579-fda683e7299c7084.js","/_next/static/chunks/5944-448b16457dce6c76.js","/_next/static/chunks/7007-0d6e62f0b2d75134.js","/_next/static/chunks/7873-94729c331d1a8315.js","/_next/static/chunks/79b386ce-04c722ba8143cb8a.js","/_next/static/chunks/8311-b9b6d18af8b3c80c.js","/_next/static/chunks/839-95619d3e787067f9.js","/_next/static/chunks/8393-8f78b04a39386629.js","/_next/static/chunks/9494-ba98c3ad461d4052.js","/_next/static/chunks/app/(app)/crm/page-f371aee908803a85.js","/_next/static/chunks/app/(app)/customer-records/page-b167111dce5922ae.js","/_next/static/chunks/app/(app)/dashboard/page-77e9554d6028e19a.js","/_next/static/chunks/app/(app)/debts/page-35d03c10c8c1c4f1.js","/_next/static/chunks/app/(app)/finance/page-9bb48315fd441928.js","/_next/static/chunks/app/(app)/hr/page-41b9f36a6781e02c.js","/_next/static/chunks/app/(app)/inventory/page-d5860f8808ac3c11.js","/_next/static/chunks/app/(app)/labels/page-28c521e6bc82ce6b.js","/_next/static/chunks/app/(app)/layout-e3d88a28c855245d.js","/_next/static/chunks/app/(app)/logs/page-0618f007d7b0eec7.js","/_next/static/chunks/app/(app)/org/page-ce41cf5460547193.js","/_next/static/chunks/app/(app)/platform-activity/page-a0d8c7387833ec13.js","/_next/static/chunks/app/(app)/platform-leads/page-9b517bce741f4430.js","/_next/static/chunks/app/(app)/platform-plans/page-de0bf926cb585c92.js","/_next/static/chunks/app/(app)/platform-registrations/page-b295412c14326c46.js","/_next/static/chunks/app/(app)/platform-seo/page-60232a49470b48fe.js","/_next/static/chunks/app/(app)/platform-subscriptions/page-455ecf664b7890c1.js","/_next/static/chunks/app/(app)/platform-team/member/page-2da8d708963cc9a1.js","/_next/static/chunks/app/(app)/platform-team/page-b08530d2761d31f9.js","/_next/static/chunks/app/(app)/platform/page-ab8ae4306b725cd6.js","/_next/static/chunks/app/(app)/purchasing/page-1dd632d7073dbe27.js","/_next/static/chunks/app/(app)/reports/page-8d834c1672ed0bcf.js","/_next/static/chunks/app/(app)/returns/page-0b6550f8d2f70f6d.js","/_next/static/chunks/app/(app)/sales/page-5ba4c40f918e62d4.js","/_next/static/chunks/app/(app)/settings/page-c0810196f42f8714.js","/_next/static/chunks/app/(app)/subscription/page-c025d309a71bd5dd.js","/_next/static/chunks/app/(app)/supplier-records/page-cc4badbad0a82585.js","/_next/static/chunks/app/(app)/users/detail/page-6b046cbfba982293.js","/_next/static/chunks/app/(app)/users/page-510b20e256c3e0ae.js","/_next/static/chunks/app/(app)/website/page-50f010be866e129c.js","/_next/static/chunks/app/(marketing)/compare/[slug]/page-3187777236565818.js","/_next/static/chunks/app/(marketing)/en/compare/[slug]/page-4b068085d7452d66.js","/_next/static/chunks/app/(marketing)/en/guides/[slug]/page-816cda1515cf6ba7.js","/_next/static/chunks/app/(marketing)/en/guides/page-3d71d5f8428eb063.js","/_next/static/chunks/app/(marketing)/en/layout-aa7e5f9d9c98defe.js","/_next/static/chunks/app/(marketing)/en/page-551acfed0a17b856.js","/_next/static/chunks/app/(marketing)/en/pricing/layout-aa7e5f9d9c98defe.js","/_next/static/chunks/app/(marketing)/en/pricing/page-13eec6e95c52ba4b.js","/_next/static/chunks/app/(marketing)/en/product/layout-aa7e5f9d9c98defe.js","/_next/static/chunks/app/(marketing)/en/product/page-0e3c087d61c9d2fc.js","/_next/static/chunks/app/(marketing)/en/register/layout-aa7e5f9d9c98defe.js","/_next/static/chunks/app/(marketing)/en/register/page-231bcbac6ca4f1bd.js","/_next/static/chunks/app/(marketing)/en/solutions/[slug]/page-1ab48d85f97c159e.js","/_next/static/chunks/app/(marketing)/en/solutions/page-8afc43dad2661da3.js","/_next/static/chunks/app/(marketing)/guides/[slug]/page-812179ccd723c5a8.js","/_next/static/chunks/app/(marketing)/guides/page-fa73a40f3f9c4349.js","/_next/static/chunks/app/(marketing)/layout-aa7e5f9d9c98defe.js","/_next/static/chunks/app/(marketing)/page-639e355b396ef47a.js","/_next/static/chunks/app/(marketing)/pricing/layout-aa7e5f9d9c98defe.js","/_next/static/chunks/app/(marketing)/pricing/page-b05ff27245a33c5d.js","/_next/static/chunks/app/(marketing)/product/layout-aa7e5f9d9c98defe.js","/_next/static/chunks/app/(marketing)/product/page-b01f4ad5192452d3.js","/_next/static/chunks/app/(marketing)/register/layout-aa7e5f9d9c98defe.js","/_next/static/chunks/app/(marketing)/register/page-3e373713373c105a.js","/_next/static/chunks/app/(marketing)/solutions/[slug]/page-0d0a5098a20b0336.js","/_next/static/chunks/app/(marketing)/solutions/page-652f778ac9a1a44a.js","/_next/static/chunks/app/_not-found/page-3a9cb9f05048cff4.js","/_next/static/chunks/app/activate-owner/layout-aa7e5f9d9c98defe.js","/_next/static/chunks/app/activate-owner/page-161a4be908add5aa.js","/_next/static/chunks/app/layout-d1f0d7ceedcc5f65.js","/_next/static/chunks/app/login/layout-aa7e5f9d9c98defe.js","/_next/static/chunks/app/login/page-2c0754bc4da3e86d.js","/_next/static/chunks/app/robots.txt/route-aa7e5f9d9c98defe.js","/_next/static/chunks/app/sitemap.xml/route-aa7e5f9d9c98defe.js","/_next/static/chunks/framework-61f74f907d7c5a15.js","/_next/static/chunks/main-app-b0dc79f8df6cdf3b.js","/_next/static/chunks/main-ea1df5cc0bedbeeb.js","/_next/static/chunks/pages/_app-5d06abb806a1b5c3.js","/_next/static/chunks/pages/_error-11078e120cb37bf3.js","/_next/static/chunks/polyfills-42372ed130431b0a.js","/_next/static/chunks/webpack-18c6324439619976.js","/_next/static/css/0f1ad28a45203602.css","/_next/static/h8ddmt1CWhfr71r4LNwRE/_buildManifest.js","/_next/static/h8ddmt1CWhfr71r4LNwRE/_ssgManifest.js","/_next/static/media/011e180705008d6f-s.woff2","/_next/static/media/01f0c602c274ea55-s.woff2","/_next/static/media/19cfc7226ec3afaa-s.woff2","/_next/static/media/1ebb550cd0a67fc6-s.p.woff2","/_next/static/media/21350d82a1f187e9-s.woff2","/_next/static/media/350b852752f8489d-s.p.woff2","/_next/static/media/3dc379dc9b5dec12-s.p.woff2","/_next/static/media/58f386aa6b1a2a92-s.woff2","/_next/static/media/5ec84f17416dda4d-s.woff2","/_next/static/media/63a79a6cf340c5d2-s.p.woff2","/_next/static/media/7ba5fb2a8c88521c-s.woff2","/_next/static/media/8e9860b6e62d6359-s.woff2","/_next/static/media/92eeb95d069020cc-s.woff2","/_next/static/media/98e207f02528a563-s.p.woff2","/_next/static/media/99dcf268bda04fe5-s.woff2","/_next/static/media/ba9851c3c22cd980-s.woff2","/_next/static/media/c5f10e9e72d35c52-s.woff2","/_next/static/media/c5fe6dc8356a8c31-s.woff2","/_next/static/media/ce401babc0566bc1-s.woff2","/_next/static/media/d29838c109ef09b4-s.woff2","/_next/static/media/d3ebbfd689654d3a-s.p.woff2","/_next/static/media/dd994fbf464986f0-s.p.woff2","/_next/static/media/df0a9ae256c0569c-s.woff2","/_next/static/media/e40af3453d7c920a-s.woff2","/_next/static/media/e4af272ccee01ff0-s.p.woff2","/_next/static/media/e97026df054cf2a3-s.woff2","/_next/static/media/ef4d5661765d0e49-s.woff2","/_next/static/media/f15f45d13243c643-s.woff2","/icons/apple-touch-icon.png","/icons/icon-192.png","/icons/icon-512.png","/icons/icon-maskable-192.png","/icons/icon-maskable-512.png","/manifest.webmanifest"];
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
