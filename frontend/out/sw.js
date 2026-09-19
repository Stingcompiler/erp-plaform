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
const BUILD = "8ean-4Y-FM8cospb0bxw_";
const CACHE = `vezano-shell-${BUILD}`;
// Every screen of the app, so the person lands on the page they asked for
// with no network — never on a different one. Filled in at build time from
// the export; the list below is the floor the PWA manifest relies on.
const PRECACHE_PAGES = ["/", "/login/", "/dashboard/", "/sales/", "/inventory/", "/returns/"];
const PRECACHE_APP_PAGES = ["/activate-owner/","/crm/","/customer-records/","/dashboard/","/debts/","/finance/","/forgot-password/","/hr/","/inventory/","/labels/","/login/","/logs/","/org/","/platform-activity/","/platform-analytics/","/platform-errors/","/platform-leads/","/platform-plans/","/platform-registrations/","/platform-seo/","/platform-subscriptions/","/platform-team/","/platform-team/member/","/platform/","/purchasing/","/reports/","/reset-password/","/returns/","/sales/","/settings/","/subscription/","/supplier-records/","/users/","/users/detail/","/website/"];
// Every hashed chunk, stylesheet and font of this build, plus the manifest
// and icons — filled in at build time from the export.
const PRECACHE_ASSETS = ["/_next/static/8ean-4Y-FM8cospb0bxw_/_buildManifest.js","/_next/static/8ean-4Y-FM8cospb0bxw_/_ssgManifest.js","/_next/static/chunks/1150-ef1e2097076e7aef.js","/_next/static/chunks/1228-5dff63c581a7eb54.js","/_next/static/chunks/1255-f456c2191ed027a9.js","/_next/static/chunks/1360-68aeac5e6d7da374.js","/_next/static/chunks/1400-edf5098c85f78768.js","/_next/static/chunks/1597-571d6d678f664d18.js","/_next/static/chunks/27-8c0b7431470a10b1.js","/_next/static/chunks/3302-585d84e085909a28.js","/_next/static/chunks/3559-6bc8e978a48da8cc.js","/_next/static/chunks/3607-bc22c35680da7b0b.js","/_next/static/chunks/4050-603e0194f207f844.js","/_next/static/chunks/4796-ddc6021c16d1db57.js","/_next/static/chunks/4bd1b696-100b9d70ed4e49c1.js","/_next/static/chunks/5053-b1373cc4e4c9c039.js","/_next/static/chunks/5596-c1bd6fa3acf30f06.js","/_next/static/chunks/6067-a95a820ee836bccf.js","/_next/static/chunks/6625-1ebe4453bbd25105.js","/_next/static/chunks/7289-ce2dea732489a2b2.js","/_next/static/chunks/7393-6366d05f7f0bbae4.js","/_next/static/chunks/8679-96c59d90137f1c06.js","/_next/static/chunks/8838-7a9b296706e9ec36.js","/_next/static/chunks/8944-ff6498a370ad1241.js","/_next/static/chunks/9475-6050b30be54033fb.js","/_next/static/chunks/app/(app)/crm/page-a2d0ee22122e51a8.js","/_next/static/chunks/app/(app)/customer-records/page-2d64e2b609475035.js","/_next/static/chunks/app/(app)/dashboard/page-313ab7a9550b120c.js","/_next/static/chunks/app/(app)/debts/page-8ae99851a878d35d.js","/_next/static/chunks/app/(app)/finance/page-6de91f81a3a44c4b.js","/_next/static/chunks/app/(app)/hr/page-ffbcb987c1903207.js","/_next/static/chunks/app/(app)/inventory/page-ad7adbde228824c5.js","/_next/static/chunks/app/(app)/labels/page-682547ce560b9c3d.js","/_next/static/chunks/app/(app)/layout-2d725c5afae34591.js","/_next/static/chunks/app/(app)/logs/page-59eea1bdfc55b010.js","/_next/static/chunks/app/(app)/org/page-f2ec03f06b2a7890.js","/_next/static/chunks/app/(app)/platform-activity/page-8e6832b91e3478a6.js","/_next/static/chunks/app/(app)/platform-analytics/page-5193d1f45c5c2431.js","/_next/static/chunks/app/(app)/platform-errors/page-767ad4d2d009b23f.js","/_next/static/chunks/app/(app)/platform-leads/page-5761789d292e14d5.js","/_next/static/chunks/app/(app)/platform-plans/page-bd11a347abb187e1.js","/_next/static/chunks/app/(app)/platform-registrations/page-fd3b6db7522527bc.js","/_next/static/chunks/app/(app)/platform-seo/page-94188d8713c7217b.js","/_next/static/chunks/app/(app)/platform-subscriptions/page-b7a9d78cfd6867e1.js","/_next/static/chunks/app/(app)/platform-team/member/page-40727dc87e52c44e.js","/_next/static/chunks/app/(app)/platform-team/page-1eda32ac25915029.js","/_next/static/chunks/app/(app)/platform/page-a525ea8707ef0c95.js","/_next/static/chunks/app/(app)/purchasing/page-e1f0b62083f50870.js","/_next/static/chunks/app/(app)/reports/page-893226044fa3f39e.js","/_next/static/chunks/app/(app)/returns/page-17d59e3b9557cee3.js","/_next/static/chunks/app/(app)/sales/page-12f927207e60b097.js","/_next/static/chunks/app/(app)/settings/page-68888880f7e21893.js","/_next/static/chunks/app/(app)/subscription/page-7ec8844f8c3cb810.js","/_next/static/chunks/app/(app)/supplier-records/page-f063b273f8e40ca4.js","/_next/static/chunks/app/(app)/users/detail/page-5e0f5260c251a9cd.js","/_next/static/chunks/app/(app)/users/page-03a912925c456211.js","/_next/static/chunks/app/(app)/website/page-1d65df7c45e6a1b3.js","/_next/static/chunks/app/(marketing)/compare/[slug]/page-f4c3c97a4c94e4e9.js","/_next/static/chunks/app/(marketing)/en/compare/[slug]/page-49decd6c7b85236a.js","/_next/static/chunks/app/(marketing)/en/guides/[slug]/page-e373cf365aabcc2c.js","/_next/static/chunks/app/(marketing)/en/guides/page-7cc1747ec2eae4f7.js","/_next/static/chunks/app/(marketing)/en/layout-54cabe5d8ce10610.js","/_next/static/chunks/app/(marketing)/en/page-87935e113fd8c1a3.js","/_next/static/chunks/app/(marketing)/en/pricing/layout-54cabe5d8ce10610.js","/_next/static/chunks/app/(marketing)/en/pricing/page-690939ad47a619a1.js","/_next/static/chunks/app/(marketing)/en/product/layout-54cabe5d8ce10610.js","/_next/static/chunks/app/(marketing)/en/product/page-d454658b5739269a.js","/_next/static/chunks/app/(marketing)/en/register/layout-54cabe5d8ce10610.js","/_next/static/chunks/app/(marketing)/en/register/page-1428d24fdcb71916.js","/_next/static/chunks/app/(marketing)/en/solutions/[slug]/page-9e4ad29ed26e7f1a.js","/_next/static/chunks/app/(marketing)/en/solutions/page-7d29b502e9e8ee2d.js","/_next/static/chunks/app/(marketing)/guides/[slug]/page-33a32f91376c5cce.js","/_next/static/chunks/app/(marketing)/guides/page-ab3b6eb2389e9040.js","/_next/static/chunks/app/(marketing)/layout-54cabe5d8ce10610.js","/_next/static/chunks/app/(marketing)/page-48490a3d6368714f.js","/_next/static/chunks/app/(marketing)/pricing/layout-54cabe5d8ce10610.js","/_next/static/chunks/app/(marketing)/pricing/page-5c30851aeadcceec.js","/_next/static/chunks/app/(marketing)/product/layout-54cabe5d8ce10610.js","/_next/static/chunks/app/(marketing)/product/page-99a3e504d3794828.js","/_next/static/chunks/app/(marketing)/register/layout-54cabe5d8ce10610.js","/_next/static/chunks/app/(marketing)/register/page-30d00ea8336bfeae.js","/_next/static/chunks/app/(marketing)/solutions/[slug]/page-d25309c32d79c1a2.js","/_next/static/chunks/app/(marketing)/solutions/page-3bc37bb2c681f70a.js","/_next/static/chunks/app/_not-found/page-2366f9337d674ec5.js","/_next/static/chunks/app/activate-owner/layout-54cabe5d8ce10610.js","/_next/static/chunks/app/activate-owner/page-d017188e456b008a.js","/_next/static/chunks/app/forgot-password/layout-54cabe5d8ce10610.js","/_next/static/chunks/app/forgot-password/page-9549d6aa37e2527a.js","/_next/static/chunks/app/layout-621270e275114106.js","/_next/static/chunks/app/login/layout-54cabe5d8ce10610.js","/_next/static/chunks/app/login/page-289f5786882cc922.js","/_next/static/chunks/app/reset-password/layout-54cabe5d8ce10610.js","/_next/static/chunks/app/reset-password/page-49f12231843957da.js","/_next/static/chunks/app/robots.txt/route-54cabe5d8ce10610.js","/_next/static/chunks/app/sitemap.xml/route-54cabe5d8ce10610.js","/_next/static/chunks/framework-4374eae96780d8a1.js","/_next/static/chunks/main-app-c234080770dca5f4.js","/_next/static/chunks/main-bad072af1eaab979.js","/_next/static/chunks/pages/_app-4b3fb5e477a0267f.js","/_next/static/chunks/pages/_error-c970d8b55ace1b48.js","/_next/static/chunks/polyfills-42372ed130431b0a.js","/_next/static/chunks/webpack-b94a8e12653a79f9.js","/_next/static/css/bae20a718a87fcd0.css","/_next/static/media/011e180705008d6f-s.woff2","/_next/static/media/01f0c602c274ea55-s.woff2","/_next/static/media/19cfc7226ec3afaa-s.woff2","/_next/static/media/1ebb550cd0a67fc6-s.p.woff2","/_next/static/media/21350d82a1f187e9-s.woff2","/_next/static/media/350b852752f8489d-s.p.woff2","/_next/static/media/3dc379dc9b5dec12-s.p.woff2","/_next/static/media/58f386aa6b1a2a92-s.woff2","/_next/static/media/5ec84f17416dda4d-s.woff2","/_next/static/media/63a79a6cf340c5d2-s.p.woff2","/_next/static/media/7ba5fb2a8c88521c-s.woff2","/_next/static/media/8e9860b6e62d6359-s.woff2","/_next/static/media/92eeb95d069020cc-s.woff2","/_next/static/media/98e207f02528a563-s.p.woff2","/_next/static/media/99dcf268bda04fe5-s.woff2","/_next/static/media/ba9851c3c22cd980-s.woff2","/_next/static/media/c5f10e9e72d35c52-s.woff2","/_next/static/media/c5fe6dc8356a8c31-s.woff2","/_next/static/media/ce401babc0566bc1-s.woff2","/_next/static/media/d29838c109ef09b4-s.woff2","/_next/static/media/d3ebbfd689654d3a-s.p.woff2","/_next/static/media/dd994fbf464986f0-s.p.woff2","/_next/static/media/df0a9ae256c0569c-s.woff2","/_next/static/media/e40af3453d7c920a-s.woff2","/_next/static/media/e4af272ccee01ff0-s.p.woff2","/_next/static/media/e97026df054cf2a3-s.woff2","/_next/static/media/ef4d5661765d0e49-s.woff2","/_next/static/media/f15f45d13243c643-s.woff2","/icons/apple-touch-icon.png","/icons/icon-192.png","/icons/icon-512.png","/icons/icon-maskable-192.png","/icons/icon-maskable-512.png","/manifest.webmanifest"];
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
