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
const BUILD = "zWmdl-SkqK0LLURvk96uK";
const CACHE = `vezano-shell-${BUILD}`;
// Routes a cashier needs reachable with no network at all.
const PRECACHE_PAGES = ["/", "/login/", "/dashboard/", "/sales/", "/inventory/", "/returns/"];
// Every hashed chunk, stylesheet and font of this build, plus the manifest
// and icons — filled in at build time from the export.
const PRECACHE_ASSETS = ["/_next/static/chunks/1228-5dff63c581a7eb54.js","/_next/static/chunks/1255-f456c2191ed027a9.js","/_next/static/chunks/1360-7d4accfc4d2e393f.js","/_next/static/chunks/1591-270b64238363a5d7.js","/_next/static/chunks/1597-571d6d678f664d18.js","/_next/static/chunks/27-1f762d3356f015e5.js","/_next/static/chunks/3302-26f824c916aff212.js","/_next/static/chunks/3607-7e8d9b7ebfd0ac0f.js","/_next/static/chunks/4050-6f7e86e7e35cfc88.js","/_next/static/chunks/475-667ffcc59be7eee1.js","/_next/static/chunks/4796-ddc6021c16d1db57.js","/_next/static/chunks/4bd1b696-100b9d70ed4e49c1.js","/_next/static/chunks/552-94fe27fe29f9cdec.js","/_next/static/chunks/5596-6d2606faad2109f5.js","/_next/static/chunks/6067-a95a820ee836bccf.js","/_next/static/chunks/6535-b6c446a1de398d18.js","/_next/static/chunks/6625-1ebe4453bbd25105.js","/_next/static/chunks/7289-ce2dea732489a2b2.js","/_next/static/chunks/8679-5591b6914d1db8fa.js","/_next/static/chunks/8838-69da96842743054b.js","/_next/static/chunks/8944-d950de3cbaa1fab1.js","/_next/static/chunks/9475-6050b30be54033fb.js","/_next/static/chunks/app/(app)/crm/page-72d1e4352cc8e544.js","/_next/static/chunks/app/(app)/customer-records/page-f797f77c96e6bf05.js","/_next/static/chunks/app/(app)/dashboard/page-cadfab52db32360b.js","/_next/static/chunks/app/(app)/debts/page-c0b1d776cc7ddd6f.js","/_next/static/chunks/app/(app)/finance/page-0f95a5c19351c807.js","/_next/static/chunks/app/(app)/hr/page-731d0a5dc7f94221.js","/_next/static/chunks/app/(app)/inventory/page-c0a34b463322ba2c.js","/_next/static/chunks/app/(app)/labels/page-77e2477d9637d145.js","/_next/static/chunks/app/(app)/layout-66774d77146065ed.js","/_next/static/chunks/app/(app)/logs/page-34de77a5489cf750.js","/_next/static/chunks/app/(app)/org/page-1a5ab7f2a60d50a5.js","/_next/static/chunks/app/(app)/platform-activity/page-795664800e46e522.js","/_next/static/chunks/app/(app)/platform-analytics/page-b149089798cd0597.js","/_next/static/chunks/app/(app)/platform-errors/page-6c3d9d360fc537b2.js","/_next/static/chunks/app/(app)/platform-leads/page-094c89fb141857fd.js","/_next/static/chunks/app/(app)/platform-plans/page-f078717af30000c3.js","/_next/static/chunks/app/(app)/platform-registrations/page-53a0c67e2c22293c.js","/_next/static/chunks/app/(app)/platform-seo/page-7812965be15f295b.js","/_next/static/chunks/app/(app)/platform-subscriptions/page-8b96526b8d939b04.js","/_next/static/chunks/app/(app)/platform-team/member/page-6822ca532bbe39c1.js","/_next/static/chunks/app/(app)/platform-team/page-01abbaa0d8eb1c0d.js","/_next/static/chunks/app/(app)/platform/page-e8bf09faf2f5b182.js","/_next/static/chunks/app/(app)/purchasing/page-516892e8571253e2.js","/_next/static/chunks/app/(app)/reports/page-f6da90429163b03f.js","/_next/static/chunks/app/(app)/returns/page-57bd19e3d54eefbc.js","/_next/static/chunks/app/(app)/sales/page-094108693eb3fa37.js","/_next/static/chunks/app/(app)/settings/page-0139656d366c48e3.js","/_next/static/chunks/app/(app)/subscription/page-b25d76dfd3aa424e.js","/_next/static/chunks/app/(app)/supplier-records/page-737325fa6d03a4a3.js","/_next/static/chunks/app/(app)/users/detail/page-a9999eb47c2b9862.js","/_next/static/chunks/app/(app)/users/page-360a305b107c8624.js","/_next/static/chunks/app/(app)/website/page-6f792deacb6d5cad.js","/_next/static/chunks/app/(marketing)/compare/[slug]/page-f4c3c97a4c94e4e9.js","/_next/static/chunks/app/(marketing)/en/compare/[slug]/page-49decd6c7b85236a.js","/_next/static/chunks/app/(marketing)/en/guides/[slug]/page-e373cf365aabcc2c.js","/_next/static/chunks/app/(marketing)/en/guides/page-7cc1747ec2eae4f7.js","/_next/static/chunks/app/(marketing)/en/layout-54cabe5d8ce10610.js","/_next/static/chunks/app/(marketing)/en/page-87935e113fd8c1a3.js","/_next/static/chunks/app/(marketing)/en/pricing/layout-54cabe5d8ce10610.js","/_next/static/chunks/app/(marketing)/en/pricing/page-690939ad47a619a1.js","/_next/static/chunks/app/(marketing)/en/product/layout-54cabe5d8ce10610.js","/_next/static/chunks/app/(marketing)/en/product/page-d454658b5739269a.js","/_next/static/chunks/app/(marketing)/en/register/layout-54cabe5d8ce10610.js","/_next/static/chunks/app/(marketing)/en/register/page-1428d24fdcb71916.js","/_next/static/chunks/app/(marketing)/en/solutions/[slug]/page-9e4ad29ed26e7f1a.js","/_next/static/chunks/app/(marketing)/en/solutions/page-7d29b502e9e8ee2d.js","/_next/static/chunks/app/(marketing)/guides/[slug]/page-33a32f91376c5cce.js","/_next/static/chunks/app/(marketing)/guides/page-ab3b6eb2389e9040.js","/_next/static/chunks/app/(marketing)/layout-54cabe5d8ce10610.js","/_next/static/chunks/app/(marketing)/page-48490a3d6368714f.js","/_next/static/chunks/app/(marketing)/pricing/layout-54cabe5d8ce10610.js","/_next/static/chunks/app/(marketing)/pricing/page-5c30851aeadcceec.js","/_next/static/chunks/app/(marketing)/product/layout-54cabe5d8ce10610.js","/_next/static/chunks/app/(marketing)/product/page-99a3e504d3794828.js","/_next/static/chunks/app/(marketing)/register/layout-54cabe5d8ce10610.js","/_next/static/chunks/app/(marketing)/register/page-30d00ea8336bfeae.js","/_next/static/chunks/app/(marketing)/solutions/[slug]/page-d25309c32d79c1a2.js","/_next/static/chunks/app/(marketing)/solutions/page-3bc37bb2c681f70a.js","/_next/static/chunks/app/_not-found/page-2366f9337d674ec5.js","/_next/static/chunks/app/activate-owner/layout-54cabe5d8ce10610.js","/_next/static/chunks/app/activate-owner/page-8ce5b9f2302e10ea.js","/_next/static/chunks/app/forgot-password/layout-54cabe5d8ce10610.js","/_next/static/chunks/app/forgot-password/page-4d79992cf1ad5fce.js","/_next/static/chunks/app/layout-39bc5d5ae0ebf0fe.js","/_next/static/chunks/app/login/layout-54cabe5d8ce10610.js","/_next/static/chunks/app/login/page-fcd9564dce13c999.js","/_next/static/chunks/app/reset-password/layout-54cabe5d8ce10610.js","/_next/static/chunks/app/reset-password/page-4ef56fe6341ef4b7.js","/_next/static/chunks/app/robots.txt/route-54cabe5d8ce10610.js","/_next/static/chunks/app/sitemap.xml/route-54cabe5d8ce10610.js","/_next/static/chunks/framework-4374eae96780d8a1.js","/_next/static/chunks/main-app-c234080770dca5f4.js","/_next/static/chunks/main-bad072af1eaab979.js","/_next/static/chunks/pages/_app-4b3fb5e477a0267f.js","/_next/static/chunks/pages/_error-c970d8b55ace1b48.js","/_next/static/chunks/polyfills-42372ed130431b0a.js","/_next/static/chunks/webpack-b94a8e12653a79f9.js","/_next/static/css/53f498ed453b3443.css","/_next/static/media/011e180705008d6f-s.woff2","/_next/static/media/01f0c602c274ea55-s.woff2","/_next/static/media/19cfc7226ec3afaa-s.woff2","/_next/static/media/1ebb550cd0a67fc6-s.p.woff2","/_next/static/media/21350d82a1f187e9-s.woff2","/_next/static/media/350b852752f8489d-s.p.woff2","/_next/static/media/3dc379dc9b5dec12-s.p.woff2","/_next/static/media/58f386aa6b1a2a92-s.woff2","/_next/static/media/5ec84f17416dda4d-s.woff2","/_next/static/media/63a79a6cf340c5d2-s.p.woff2","/_next/static/media/7ba5fb2a8c88521c-s.woff2","/_next/static/media/8e9860b6e62d6359-s.woff2","/_next/static/media/92eeb95d069020cc-s.woff2","/_next/static/media/98e207f02528a563-s.p.woff2","/_next/static/media/99dcf268bda04fe5-s.woff2","/_next/static/media/ba9851c3c22cd980-s.woff2","/_next/static/media/c5f10e9e72d35c52-s.woff2","/_next/static/media/c5fe6dc8356a8c31-s.woff2","/_next/static/media/ce401babc0566bc1-s.woff2","/_next/static/media/d29838c109ef09b4-s.woff2","/_next/static/media/d3ebbfd689654d3a-s.p.woff2","/_next/static/media/dd994fbf464986f0-s.p.woff2","/_next/static/media/df0a9ae256c0569c-s.woff2","/_next/static/media/e40af3453d7c920a-s.woff2","/_next/static/media/e4af272ccee01ff0-s.p.woff2","/_next/static/media/e97026df054cf2a3-s.woff2","/_next/static/media/ef4d5661765d0e49-s.woff2","/_next/static/media/f15f45d13243c643-s.woff2","/_next/static/zWmdl-SkqK0LLURvk96uK/_buildManifest.js","/_next/static/zWmdl-SkqK0LLURvk96uK/_ssgManifest.js","/icons/apple-touch-icon.png","/icons/icon-192.png","/icons/icon-512.png","/icons/icon-maskable-192.png","/icons/icon-maskable-512.png","/manifest.webmanifest"];
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
