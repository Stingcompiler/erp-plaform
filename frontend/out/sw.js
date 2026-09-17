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
const BUILD = "4r1F1n0SJbKVxEjK9DjxW";
const CACHE = `vezano-shell-${BUILD}`;
// Routes a cashier needs reachable with no network at all.
const PRECACHE_PAGES = ["/", "/login/", "/dashboard/", "/sales/", "/inventory/", "/returns/"];
// Every hashed chunk, stylesheet and font of this build, plus the manifest
// and icons — filled in at build time from the export.
const PRECACHE_ASSETS = ["/_next/static/4r1F1n0SJbKVxEjK9DjxW/_buildManifest.js","/_next/static/4r1F1n0SJbKVxEjK9DjxW/_ssgManifest.js","/_next/static/chunks/1654-1b7a339001bf0bdd.js","/_next/static/chunks/2215-56cc1f43fefc93a7.js","/_next/static/chunks/2667-3f126880db19a705.js","/_next/static/chunks/3310-0c2e0aecbc41fc19.js","/_next/static/chunks/4008-b4be416bf29756e4.js","/_next/static/chunks/4868-2642b564631c8d0c.js","/_next/static/chunks/5084-d926eb03d1f330d6.js","/_next/static/chunks/5141-4d219d8fb7fdf70f.js","/_next/static/chunks/5306-392f08460957c2b9.js","/_next/static/chunks/5462-c897333e07268651.js","/_next/static/chunks/579-fda683e7299c7084.js","/_next/static/chunks/5944-448b16457dce6c76.js","/_next/static/chunks/7007-0d6e62f0b2d75134.js","/_next/static/chunks/7873-94729c331d1a8315.js","/_next/static/chunks/79b386ce-04c722ba8143cb8a.js","/_next/static/chunks/8311-8af3873c4486b500.js","/_next/static/chunks/839-95619d3e787067f9.js","/_next/static/chunks/8393-8f78b04a39386629.js","/_next/static/chunks/8567-4b0f2d7bdd756651.js","/_next/static/chunks/9494-ba98c3ad461d4052.js","/_next/static/chunks/app/(app)/crm/page-ce33267535d01661.js","/_next/static/chunks/app/(app)/customer-records/page-fbd948f04c0c1012.js","/_next/static/chunks/app/(app)/dashboard/page-66902b7b6a25df26.js","/_next/static/chunks/app/(app)/debts/page-b34d52d9d3b3b5b3.js","/_next/static/chunks/app/(app)/finance/page-9eea4462c6d82d2c.js","/_next/static/chunks/app/(app)/hr/page-9435ce07a5603530.js","/_next/static/chunks/app/(app)/inventory/page-0e4830fe9479fc75.js","/_next/static/chunks/app/(app)/labels/page-736bd10a935ebfe4.js","/_next/static/chunks/app/(app)/layout-6cffa829e98d0a59.js","/_next/static/chunks/app/(app)/logs/page-5295923145641447.js","/_next/static/chunks/app/(app)/org/page-cd935ebfc880a361.js","/_next/static/chunks/app/(app)/platform-activity/page-ece6dd5686fad7e2.js","/_next/static/chunks/app/(app)/platform-leads/page-5ba9c29b42575882.js","/_next/static/chunks/app/(app)/platform-plans/page-e745c8000ed2fb6c.js","/_next/static/chunks/app/(app)/platform-registrations/page-3330131d3d73dbe3.js","/_next/static/chunks/app/(app)/platform-seo/page-d4132dd8b693595e.js","/_next/static/chunks/app/(app)/platform-subscriptions/page-3a1b98fe5f494a41.js","/_next/static/chunks/app/(app)/platform-team/member/page-9b048d70f666fbd4.js","/_next/static/chunks/app/(app)/platform-team/page-dc96827e437603f6.js","/_next/static/chunks/app/(app)/platform/page-7f8e3ac107d42c2e.js","/_next/static/chunks/app/(app)/purchasing/page-54c1ebc9e98e51ec.js","/_next/static/chunks/app/(app)/reports/page-1f1c991aec2a9425.js","/_next/static/chunks/app/(app)/returns/page-a39afcdbaabdd614.js","/_next/static/chunks/app/(app)/sales/page-900c1d31953738eb.js","/_next/static/chunks/app/(app)/settings/page-84bd3117a68d67b8.js","/_next/static/chunks/app/(app)/subscription/page-544cda2fb08c1b86.js","/_next/static/chunks/app/(app)/supplier-records/page-e5cc7fddbf41e0c8.js","/_next/static/chunks/app/(app)/users/detail/page-7b5bfbdb2b27d2c7.js","/_next/static/chunks/app/(app)/users/page-58824cbf9f424ca6.js","/_next/static/chunks/app/(app)/website/page-6a5b20041c32421e.js","/_next/static/chunks/app/(marketing)/compare/[slug]/page-0752d7210b448928.js","/_next/static/chunks/app/(marketing)/en/compare/[slug]/page-58318b88f8699988.js","/_next/static/chunks/app/(marketing)/en/guides/[slug]/page-47d3801420f36259.js","/_next/static/chunks/app/(marketing)/en/guides/page-e11b661e28cf4195.js","/_next/static/chunks/app/(marketing)/en/layout-aa7e5f9d9c98defe.js","/_next/static/chunks/app/(marketing)/en/page-078ce0c459f3d66b.js","/_next/static/chunks/app/(marketing)/en/pricing/layout-aa7e5f9d9c98defe.js","/_next/static/chunks/app/(marketing)/en/pricing/page-a80b991e27a415b2.js","/_next/static/chunks/app/(marketing)/en/product/layout-aa7e5f9d9c98defe.js","/_next/static/chunks/app/(marketing)/en/product/page-f5a000742616102e.js","/_next/static/chunks/app/(marketing)/en/register/layout-aa7e5f9d9c98defe.js","/_next/static/chunks/app/(marketing)/en/register/page-8e1af166f97a8f60.js","/_next/static/chunks/app/(marketing)/en/solutions/[slug]/page-271c2c3a186395d5.js","/_next/static/chunks/app/(marketing)/en/solutions/page-37bb84af092ec5ed.js","/_next/static/chunks/app/(marketing)/guides/[slug]/page-32f3951da52fb1ff.js","/_next/static/chunks/app/(marketing)/guides/page-daec107f6b59140d.js","/_next/static/chunks/app/(marketing)/layout-aa7e5f9d9c98defe.js","/_next/static/chunks/app/(marketing)/page-66e819a04ce95f04.js","/_next/static/chunks/app/(marketing)/pricing/layout-aa7e5f9d9c98defe.js","/_next/static/chunks/app/(marketing)/pricing/page-1996c7be63a9b13d.js","/_next/static/chunks/app/(marketing)/product/layout-aa7e5f9d9c98defe.js","/_next/static/chunks/app/(marketing)/product/page-879ea1fa649d9fbe.js","/_next/static/chunks/app/(marketing)/register/layout-aa7e5f9d9c98defe.js","/_next/static/chunks/app/(marketing)/register/page-e0441bfa3c4ba053.js","/_next/static/chunks/app/(marketing)/solutions/[slug]/page-81b79c327f20653c.js","/_next/static/chunks/app/(marketing)/solutions/page-980266c8e17c3287.js","/_next/static/chunks/app/_not-found/page-3a9cb9f05048cff4.js","/_next/static/chunks/app/activate-owner/layout-aa7e5f9d9c98defe.js","/_next/static/chunks/app/activate-owner/page-9b9c278080c22764.js","/_next/static/chunks/app/layout-8daf605b2d07126d.js","/_next/static/chunks/app/login/layout-aa7e5f9d9c98defe.js","/_next/static/chunks/app/login/page-5b78f342642ba1c9.js","/_next/static/chunks/app/robots.txt/route-aa7e5f9d9c98defe.js","/_next/static/chunks/app/sitemap.xml/route-aa7e5f9d9c98defe.js","/_next/static/chunks/framework-61f74f907d7c5a15.js","/_next/static/chunks/main-app-b0dc79f8df6cdf3b.js","/_next/static/chunks/main-ea1df5cc0bedbeeb.js","/_next/static/chunks/pages/_app-5d06abb806a1b5c3.js","/_next/static/chunks/pages/_error-11078e120cb37bf3.js","/_next/static/chunks/polyfills-42372ed130431b0a.js","/_next/static/chunks/webpack-18c6324439619976.js","/_next/static/css/0f1ad28a45203602.css","/_next/static/media/011e180705008d6f-s.woff2","/_next/static/media/01f0c602c274ea55-s.woff2","/_next/static/media/19cfc7226ec3afaa-s.woff2","/_next/static/media/1ebb550cd0a67fc6-s.p.woff2","/_next/static/media/21350d82a1f187e9-s.woff2","/_next/static/media/350b852752f8489d-s.p.woff2","/_next/static/media/3dc379dc9b5dec12-s.p.woff2","/_next/static/media/58f386aa6b1a2a92-s.woff2","/_next/static/media/5ec84f17416dda4d-s.woff2","/_next/static/media/63a79a6cf340c5d2-s.p.woff2","/_next/static/media/7ba5fb2a8c88521c-s.woff2","/_next/static/media/8e9860b6e62d6359-s.woff2","/_next/static/media/92eeb95d069020cc-s.woff2","/_next/static/media/98e207f02528a563-s.p.woff2","/_next/static/media/99dcf268bda04fe5-s.woff2","/_next/static/media/ba9851c3c22cd980-s.woff2","/_next/static/media/c5f10e9e72d35c52-s.woff2","/_next/static/media/c5fe6dc8356a8c31-s.woff2","/_next/static/media/ce401babc0566bc1-s.woff2","/_next/static/media/d29838c109ef09b4-s.woff2","/_next/static/media/d3ebbfd689654d3a-s.p.woff2","/_next/static/media/dd994fbf464986f0-s.p.woff2","/_next/static/media/df0a9ae256c0569c-s.woff2","/_next/static/media/e40af3453d7c920a-s.woff2","/_next/static/media/e4af272ccee01ff0-s.p.woff2","/_next/static/media/e97026df054cf2a3-s.woff2","/_next/static/media/ef4d5661765d0e49-s.woff2","/_next/static/media/f15f45d13243c643-s.woff2","/icons/apple-touch-icon.png","/icons/icon-192.png","/icons/icon-512.png","/icons/icon-maskable-192.png","/icons/icon-maskable-512.png","/manifest.webmanifest"];
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
