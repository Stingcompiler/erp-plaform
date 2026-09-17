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
const BUILD = "nRqxdccTovv-W7ao8c0rT";
const CACHE = `vezano-shell-${BUILD}`;
// Routes a cashier needs reachable with no network at all.
const PRECACHE_PAGES = ["/", "/login/", "/dashboard/", "/sales/", "/inventory/", "/returns/"];
// Every hashed chunk, stylesheet and font of this build, plus the manifest
// and icons — filled in at build time from the export.
const PRECACHE_ASSETS = ["/_next/static/chunks/1654-1b7a339001bf0bdd.js","/_next/static/chunks/2215-56cc1f43fefc93a7.js","/_next/static/chunks/2667-3f126880db19a705.js","/_next/static/chunks/3310-0c2e0aecbc41fc19.js","/_next/static/chunks/4008-b4be416bf29756e4.js","/_next/static/chunks/4868-2642b564631c8d0c.js","/_next/static/chunks/5084-d926eb03d1f330d6.js","/_next/static/chunks/5139-618133e8a98f8e9d.js","/_next/static/chunks/5141-4d219d8fb7fdf70f.js","/_next/static/chunks/5306-392f08460957c2b9.js","/_next/static/chunks/5462-c897333e07268651.js","/_next/static/chunks/579-fda683e7299c7084.js","/_next/static/chunks/5944-448b16457dce6c76.js","/_next/static/chunks/7007-0d6e62f0b2d75134.js","/_next/static/chunks/7873-94729c331d1a8315.js","/_next/static/chunks/79b386ce-04c722ba8143cb8a.js","/_next/static/chunks/8311-dc62708fbbb406c8.js","/_next/static/chunks/839-95619d3e787067f9.js","/_next/static/chunks/8393-8f78b04a39386629.js","/_next/static/chunks/9494-ba98c3ad461d4052.js","/_next/static/chunks/app/(app)/crm/page-1b76edc7c30fa009.js","/_next/static/chunks/app/(app)/customer-records/page-d035c3b8fe65cffc.js","/_next/static/chunks/app/(app)/dashboard/page-6e3f0376458af388.js","/_next/static/chunks/app/(app)/debts/page-01ce4e8e0d67a814.js","/_next/static/chunks/app/(app)/finance/page-23258af5d5fba6dd.js","/_next/static/chunks/app/(app)/hr/page-bae784996dca2932.js","/_next/static/chunks/app/(app)/inventory/page-3c7b06542228ec1f.js","/_next/static/chunks/app/(app)/labels/page-1869c0ed4507fcb5.js","/_next/static/chunks/app/(app)/layout-b5da2443905c73ae.js","/_next/static/chunks/app/(app)/logs/page-d014adc3d866403f.js","/_next/static/chunks/app/(app)/org/page-0f2373ee3437279e.js","/_next/static/chunks/app/(app)/platform-activity/page-0a0f250fd90acc09.js","/_next/static/chunks/app/(app)/platform-leads/page-233cdba744cfed43.js","/_next/static/chunks/app/(app)/platform-plans/page-29f2daa678456c3c.js","/_next/static/chunks/app/(app)/platform-registrations/page-3706ee68695f3b86.js","/_next/static/chunks/app/(app)/platform-seo/page-afb44d48164168d5.js","/_next/static/chunks/app/(app)/platform-subscriptions/page-fce61c4b1a60ecd4.js","/_next/static/chunks/app/(app)/platform-team/member/page-f163eb5640cf95d3.js","/_next/static/chunks/app/(app)/platform-team/page-1e89cded7a26200d.js","/_next/static/chunks/app/(app)/platform/page-4af5b9e9951ae0c8.js","/_next/static/chunks/app/(app)/purchasing/page-2c11b57f56394597.js","/_next/static/chunks/app/(app)/reports/page-71aac05936740dbc.js","/_next/static/chunks/app/(app)/returns/page-3a4657cdf8ff0e2a.js","/_next/static/chunks/app/(app)/sales/page-3e950c944c757934.js","/_next/static/chunks/app/(app)/settings/page-8bc23319b4b34535.js","/_next/static/chunks/app/(app)/subscription/page-8521c033f7ef2af3.js","/_next/static/chunks/app/(app)/supplier-records/page-8ef833bedc591fc6.js","/_next/static/chunks/app/(app)/users/detail/page-83c1af7551f14e76.js","/_next/static/chunks/app/(app)/users/page-cdc1dc21d55a443d.js","/_next/static/chunks/app/(app)/website/page-b46fdbf81716afbf.js","/_next/static/chunks/app/(marketing)/compare/[slug]/page-98812224fb025d4a.js","/_next/static/chunks/app/(marketing)/en/compare/[slug]/page-7f7e088b7a402bed.js","/_next/static/chunks/app/(marketing)/en/guides/[slug]/page-631cd32a4c34de6c.js","/_next/static/chunks/app/(marketing)/en/guides/page-66228623700d8282.js","/_next/static/chunks/app/(marketing)/en/layout-aa7e5f9d9c98defe.js","/_next/static/chunks/app/(marketing)/en/page-517fe4fff62491d1.js","/_next/static/chunks/app/(marketing)/en/pricing/layout-aa7e5f9d9c98defe.js","/_next/static/chunks/app/(marketing)/en/pricing/page-b0b95a799a1a871f.js","/_next/static/chunks/app/(marketing)/en/product/layout-aa7e5f9d9c98defe.js","/_next/static/chunks/app/(marketing)/en/product/page-7f4b86297b5c51dc.js","/_next/static/chunks/app/(marketing)/en/register/layout-aa7e5f9d9c98defe.js","/_next/static/chunks/app/(marketing)/en/register/page-162b8c2835d1fb21.js","/_next/static/chunks/app/(marketing)/en/solutions/[slug]/page-7cd17f8b6e0fcbac.js","/_next/static/chunks/app/(marketing)/en/solutions/page-c9ebea9e100f595e.js","/_next/static/chunks/app/(marketing)/guides/[slug]/page-c11ada14693d6778.js","/_next/static/chunks/app/(marketing)/guides/page-a868fee13b684554.js","/_next/static/chunks/app/(marketing)/layout-aa7e5f9d9c98defe.js","/_next/static/chunks/app/(marketing)/page-8c81f30c5720a822.js","/_next/static/chunks/app/(marketing)/pricing/layout-aa7e5f9d9c98defe.js","/_next/static/chunks/app/(marketing)/pricing/page-2524275353a5c9fe.js","/_next/static/chunks/app/(marketing)/product/layout-aa7e5f9d9c98defe.js","/_next/static/chunks/app/(marketing)/product/page-42a2f9766c34507c.js","/_next/static/chunks/app/(marketing)/register/layout-aa7e5f9d9c98defe.js","/_next/static/chunks/app/(marketing)/register/page-1cbd4fbdaedcf542.js","/_next/static/chunks/app/(marketing)/solutions/[slug]/page-f0bae22c8df92bc7.js","/_next/static/chunks/app/(marketing)/solutions/page-14fb84f8f270a9ad.js","/_next/static/chunks/app/_not-found/page-3a9cb9f05048cff4.js","/_next/static/chunks/app/activate-owner/layout-aa7e5f9d9c98defe.js","/_next/static/chunks/app/activate-owner/page-7357b1bf8e00887d.js","/_next/static/chunks/app/layout-753a23aba17792cf.js","/_next/static/chunks/app/login/layout-aa7e5f9d9c98defe.js","/_next/static/chunks/app/login/page-cd9e91ce7f46dbd6.js","/_next/static/chunks/app/robots.txt/route-aa7e5f9d9c98defe.js","/_next/static/chunks/app/sitemap.xml/route-aa7e5f9d9c98defe.js","/_next/static/chunks/framework-61f74f907d7c5a15.js","/_next/static/chunks/main-app-b0dc79f8df6cdf3b.js","/_next/static/chunks/main-ea1df5cc0bedbeeb.js","/_next/static/chunks/pages/_app-5d06abb806a1b5c3.js","/_next/static/chunks/pages/_error-11078e120cb37bf3.js","/_next/static/chunks/polyfills-42372ed130431b0a.js","/_next/static/chunks/webpack-18c6324439619976.js","/_next/static/css/0f1ad28a45203602.css","/_next/static/media/011e180705008d6f-s.woff2","/_next/static/media/01f0c602c274ea55-s.woff2","/_next/static/media/19cfc7226ec3afaa-s.woff2","/_next/static/media/1ebb550cd0a67fc6-s.p.woff2","/_next/static/media/21350d82a1f187e9-s.woff2","/_next/static/media/350b852752f8489d-s.p.woff2","/_next/static/media/3dc379dc9b5dec12-s.p.woff2","/_next/static/media/58f386aa6b1a2a92-s.woff2","/_next/static/media/5ec84f17416dda4d-s.woff2","/_next/static/media/63a79a6cf340c5d2-s.p.woff2","/_next/static/media/7ba5fb2a8c88521c-s.woff2","/_next/static/media/8e9860b6e62d6359-s.woff2","/_next/static/media/92eeb95d069020cc-s.woff2","/_next/static/media/98e207f02528a563-s.p.woff2","/_next/static/media/99dcf268bda04fe5-s.woff2","/_next/static/media/ba9851c3c22cd980-s.woff2","/_next/static/media/c5f10e9e72d35c52-s.woff2","/_next/static/media/c5fe6dc8356a8c31-s.woff2","/_next/static/media/ce401babc0566bc1-s.woff2","/_next/static/media/d29838c109ef09b4-s.woff2","/_next/static/media/d3ebbfd689654d3a-s.p.woff2","/_next/static/media/dd994fbf464986f0-s.p.woff2","/_next/static/media/df0a9ae256c0569c-s.woff2","/_next/static/media/e40af3453d7c920a-s.woff2","/_next/static/media/e4af272ccee01ff0-s.p.woff2","/_next/static/media/e97026df054cf2a3-s.woff2","/_next/static/media/ef4d5661765d0e49-s.woff2","/_next/static/media/f15f45d13243c643-s.woff2","/_next/static/nRqxdccTovv-W7ao8c0rT/_buildManifest.js","/_next/static/nRqxdccTovv-W7ao8c0rT/_ssgManifest.js","/icons/apple-touch-icon.png","/icons/icon-192.png","/icons/icon-512.png","/icons/icon-maskable-192.png","/icons/icon-maskable-512.png","/manifest.webmanifest"];
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
