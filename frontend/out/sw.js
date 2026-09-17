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
const BUILD = "10TwzROak7lHNZTV29qKD";
const CACHE = `vezano-shell-${BUILD}`;
// Routes a cashier needs reachable with no network at all.
const PRECACHE_PAGES = ["/", "/login/", "/dashboard/", "/sales/", "/inventory/", "/returns/"];
// Every hashed chunk, stylesheet and font of this build, plus the manifest
// and icons — filled in at build time from the export.
const PRECACHE_ASSETS = ["/_next/static/10TwzROak7lHNZTV29qKD/_buildManifest.js","/_next/static/10TwzROak7lHNZTV29qKD/_ssgManifest.js","/_next/static/chunks/1654-cfae15037ea63f50.js","/_next/static/chunks/2215-56cc1f43fefc93a7.js","/_next/static/chunks/2667-3f126880db19a705.js","/_next/static/chunks/3310-0c2e0aecbc41fc19.js","/_next/static/chunks/4008-b4be416bf29756e4.js","/_next/static/chunks/4868-2642b564631c8d0c.js","/_next/static/chunks/5084-d926eb03d1f330d6.js","/_next/static/chunks/5141-bbbc731cd11b7ae7.js","/_next/static/chunks/5306-392f08460957c2b9.js","/_next/static/chunks/5462-c897333e07268651.js","/_next/static/chunks/579-fda683e7299c7084.js","/_next/static/chunks/5944-448b16457dce6c76.js","/_next/static/chunks/7007-0d6e62f0b2d75134.js","/_next/static/chunks/7873-94729c331d1a8315.js","/_next/static/chunks/79b386ce-04c722ba8143cb8a.js","/_next/static/chunks/8311-763666f31be700ac.js","/_next/static/chunks/8375-89d23fa4301eba61.js","/_next/static/chunks/839-95619d3e787067f9.js","/_next/static/chunks/8393-8f78b04a39386629.js","/_next/static/chunks/9494-ba98c3ad461d4052.js","/_next/static/chunks/app/(app)/crm/page-e7bda73826abefeb.js","/_next/static/chunks/app/(app)/customer-records/page-3ff621dc5ed1fe84.js","/_next/static/chunks/app/(app)/dashboard/page-41bc7e6a68380d56.js","/_next/static/chunks/app/(app)/debts/page-1d38d694f48511ee.js","/_next/static/chunks/app/(app)/finance/page-3ff8f40d4edffcdc.js","/_next/static/chunks/app/(app)/hr/page-0364cc738e7e0cb6.js","/_next/static/chunks/app/(app)/inventory/page-48d92d2507d33e60.js","/_next/static/chunks/app/(app)/labels/page-49c834b59d493e57.js","/_next/static/chunks/app/(app)/layout-a6e1d2b911261939.js","/_next/static/chunks/app/(app)/logs/page-4f0bb5d9a6ef658c.js","/_next/static/chunks/app/(app)/org/page-56202934a2cf4641.js","/_next/static/chunks/app/(app)/platform-activity/page-154fa61974c583ac.js","/_next/static/chunks/app/(app)/platform-leads/page-326dd06d967f71b5.js","/_next/static/chunks/app/(app)/platform-plans/page-33989958bb3463a2.js","/_next/static/chunks/app/(app)/platform-registrations/page-6e15d062cc1ed4e8.js","/_next/static/chunks/app/(app)/platform-seo/page-8d6f9b29844d3320.js","/_next/static/chunks/app/(app)/platform-subscriptions/page-4d75aa3fb24a7efe.js","/_next/static/chunks/app/(app)/platform-team/member/page-ad5d2bf0a96e25d8.js","/_next/static/chunks/app/(app)/platform-team/page-eb90a370abe8fa93.js","/_next/static/chunks/app/(app)/platform/page-ab43ca7656cbb6c7.js","/_next/static/chunks/app/(app)/purchasing/page-2c430b1bff6f329e.js","/_next/static/chunks/app/(app)/reports/page-7f812472deb65f75.js","/_next/static/chunks/app/(app)/returns/page-eed77574433653bd.js","/_next/static/chunks/app/(app)/sales/page-b387058a9f68855d.js","/_next/static/chunks/app/(app)/settings/page-e991691f9013e8ad.js","/_next/static/chunks/app/(app)/subscription/page-b99436dfc2cd6610.js","/_next/static/chunks/app/(app)/supplier-records/page-38960921ff876bb1.js","/_next/static/chunks/app/(app)/users/detail/page-d731a99436c48894.js","/_next/static/chunks/app/(app)/users/page-cc4f00c927df10e8.js","/_next/static/chunks/app/(app)/website/page-8bf7e8b0d25e8575.js","/_next/static/chunks/app/(marketing)/compare/[slug]/page-a9ce038e6be853f7.js","/_next/static/chunks/app/(marketing)/en/compare/[slug]/page-77927e47c66c8565.js","/_next/static/chunks/app/(marketing)/en/guides/[slug]/page-9332d5d71a1c84a1.js","/_next/static/chunks/app/(marketing)/en/guides/page-0ba1425a42f6fa16.js","/_next/static/chunks/app/(marketing)/en/layout-aa7e5f9d9c98defe.js","/_next/static/chunks/app/(marketing)/en/page-af71b2dbbff84487.js","/_next/static/chunks/app/(marketing)/en/pricing/layout-aa7e5f9d9c98defe.js","/_next/static/chunks/app/(marketing)/en/pricing/page-4a4eb587a85e63de.js","/_next/static/chunks/app/(marketing)/en/product/layout-aa7e5f9d9c98defe.js","/_next/static/chunks/app/(marketing)/en/product/page-bcf8ca00a7cfeb78.js","/_next/static/chunks/app/(marketing)/en/register/layout-aa7e5f9d9c98defe.js","/_next/static/chunks/app/(marketing)/en/register/page-91554d80adf1d1db.js","/_next/static/chunks/app/(marketing)/en/solutions/[slug]/page-67a3aa5f94f65681.js","/_next/static/chunks/app/(marketing)/en/solutions/page-6c348a6913c412e6.js","/_next/static/chunks/app/(marketing)/guides/[slug]/page-11417136b803b3bf.js","/_next/static/chunks/app/(marketing)/guides/page-8dbef2d912ec53e4.js","/_next/static/chunks/app/(marketing)/layout-aa7e5f9d9c98defe.js","/_next/static/chunks/app/(marketing)/page-35d65bc6d11a7fb5.js","/_next/static/chunks/app/(marketing)/pricing/layout-aa7e5f9d9c98defe.js","/_next/static/chunks/app/(marketing)/pricing/page-23c9b1a0fd7e6b27.js","/_next/static/chunks/app/(marketing)/product/layout-aa7e5f9d9c98defe.js","/_next/static/chunks/app/(marketing)/product/page-823450b4ed87cbfd.js","/_next/static/chunks/app/(marketing)/register/layout-aa7e5f9d9c98defe.js","/_next/static/chunks/app/(marketing)/register/page-d48fbf3e06795143.js","/_next/static/chunks/app/(marketing)/solutions/[slug]/page-2bb218969864f74f.js","/_next/static/chunks/app/(marketing)/solutions/page-12ab666eaa32557a.js","/_next/static/chunks/app/_not-found/page-3a9cb9f05048cff4.js","/_next/static/chunks/app/activate-owner/layout-aa7e5f9d9c98defe.js","/_next/static/chunks/app/activate-owner/page-02cd37b5197ec9bb.js","/_next/static/chunks/app/layout-fb7850c3b7af311b.js","/_next/static/chunks/app/login/layout-aa7e5f9d9c98defe.js","/_next/static/chunks/app/login/page-31977bf42bd9c5fc.js","/_next/static/chunks/app/robots.txt/route-aa7e5f9d9c98defe.js","/_next/static/chunks/app/sitemap.xml/route-aa7e5f9d9c98defe.js","/_next/static/chunks/framework-61f74f907d7c5a15.js","/_next/static/chunks/main-app-b0dc79f8df6cdf3b.js","/_next/static/chunks/main-ea1df5cc0bedbeeb.js","/_next/static/chunks/pages/_app-5d06abb806a1b5c3.js","/_next/static/chunks/pages/_error-11078e120cb37bf3.js","/_next/static/chunks/polyfills-42372ed130431b0a.js","/_next/static/chunks/webpack-18c6324439619976.js","/_next/static/css/0f1ad28a45203602.css","/_next/static/media/011e180705008d6f-s.woff2","/_next/static/media/01f0c602c274ea55-s.woff2","/_next/static/media/19cfc7226ec3afaa-s.woff2","/_next/static/media/1ebb550cd0a67fc6-s.p.woff2","/_next/static/media/21350d82a1f187e9-s.woff2","/_next/static/media/350b852752f8489d-s.p.woff2","/_next/static/media/3dc379dc9b5dec12-s.p.woff2","/_next/static/media/58f386aa6b1a2a92-s.woff2","/_next/static/media/5ec84f17416dda4d-s.woff2","/_next/static/media/63a79a6cf340c5d2-s.p.woff2","/_next/static/media/7ba5fb2a8c88521c-s.woff2","/_next/static/media/8e9860b6e62d6359-s.woff2","/_next/static/media/92eeb95d069020cc-s.woff2","/_next/static/media/98e207f02528a563-s.p.woff2","/_next/static/media/99dcf268bda04fe5-s.woff2","/_next/static/media/ba9851c3c22cd980-s.woff2","/_next/static/media/c5f10e9e72d35c52-s.woff2","/_next/static/media/c5fe6dc8356a8c31-s.woff2","/_next/static/media/ce401babc0566bc1-s.woff2","/_next/static/media/d29838c109ef09b4-s.woff2","/_next/static/media/d3ebbfd689654d3a-s.p.woff2","/_next/static/media/dd994fbf464986f0-s.p.woff2","/_next/static/media/df0a9ae256c0569c-s.woff2","/_next/static/media/e40af3453d7c920a-s.woff2","/_next/static/media/e4af272ccee01ff0-s.p.woff2","/_next/static/media/e97026df054cf2a3-s.woff2","/_next/static/media/ef4d5661765d0e49-s.woff2","/_next/static/media/f15f45d13243c643-s.woff2","/icons/apple-touch-icon.png","/icons/icon-192.png","/icons/icon-512.png","/icons/icon-maskable-192.png","/icons/icon-maskable-512.png","/manifest.webmanifest"];
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
