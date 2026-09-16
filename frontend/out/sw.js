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
const BUILD = "utFn4T7XXIrGit8bUdMrh";
const CACHE = `vezano-shell-${BUILD}`;
// Routes a cashier needs reachable with no network at all.
const PRECACHE_PAGES = ["/", "/login/", "/dashboard/", "/sales/", "/inventory/", "/returns/"];
// Every hashed chunk, stylesheet and font of this build, plus the manifest
// and icons — filled in at build time from the export.
const PRECACHE_ASSETS = ["/_next/static/chunks/2094-f1a0ccda8a8ea746.js","/_next/static/chunks/2595-a56291371d2228c1.js","/_next/static/chunks/3809-10fcd2fadb471371.js","/_next/static/chunks/4779-a0f1e9b437b90f4c.js","/_next/static/chunks/486-028be7a6af4a2cac.js","/_next/static/chunks/4960-5c36080d5e3222f5.js","/_next/static/chunks/5973-451f9e26e58e263c.js","/_next/static/chunks/6048-51a38bf3018bc347.js","/_next/static/chunks/6131-72c7a6017f4a7c8d.js","/_next/static/chunks/6159-60f7692a6c90ad5d.js","/_next/static/chunks/6641-d0158c4133dfe1e2.js","/_next/static/chunks/7395-bb36362559ce4b16.js","/_next/static/chunks/7682-3a108883f60ef56d.js","/_next/static/chunks/7812-a166cec3a58ecbac.js","/_next/static/chunks/9046-b01df8fb906fdf3f.js","/_next/static/chunks/9311-987bd483ed10d3a8.js","/_next/static/chunks/9505-1197f94166ee086a.js","/_next/static/chunks/96e575d4-b4ecc6041b2b9a52.js","/_next/static/chunks/app/(app)/crm/page-9a749528b72cb3b6.js","/_next/static/chunks/app/(app)/customer-records/page-591e738f282590ac.js","/_next/static/chunks/app/(app)/dashboard/page-9db05bb6be81cf11.js","/_next/static/chunks/app/(app)/debts/page-375424ead3530e25.js","/_next/static/chunks/app/(app)/finance/page-d7b852d95568d869.js","/_next/static/chunks/app/(app)/hr/page-4fe321fdb49a9698.js","/_next/static/chunks/app/(app)/inventory/page-7448e8dcaafe3efb.js","/_next/static/chunks/app/(app)/labels/page-a68cfbd0e9edb112.js","/_next/static/chunks/app/(app)/layout-53bcc65fedc3b441.js","/_next/static/chunks/app/(app)/logs/page-af7383d0bea567e8.js","/_next/static/chunks/app/(app)/org/page-6e5c264c96df7406.js","/_next/static/chunks/app/(app)/platform-activity/page-b5d7c9b2f85dcd5d.js","/_next/static/chunks/app/(app)/platform-leads/page-5098424e88830cd0.js","/_next/static/chunks/app/(app)/platform-plans/page-176285d05ae1f81c.js","/_next/static/chunks/app/(app)/platform-registrations/page-86acbac17e663343.js","/_next/static/chunks/app/(app)/platform-seo/page-7d60e6c011a3e7ac.js","/_next/static/chunks/app/(app)/platform-subscriptions/page-5389123035956eee.js","/_next/static/chunks/app/(app)/platform-team/member/page-c02d6029525febba.js","/_next/static/chunks/app/(app)/platform-team/page-500d5f8986e47d3c.js","/_next/static/chunks/app/(app)/platform/page-2697e1d56b3576b3.js","/_next/static/chunks/app/(app)/purchasing/page-d6ebaca4ce69ca93.js","/_next/static/chunks/app/(app)/reports/page-f0780808e3612dd3.js","/_next/static/chunks/app/(app)/returns/page-9a3be3d138c0e186.js","/_next/static/chunks/app/(app)/sales/page-4969b60b96c2bd5a.js","/_next/static/chunks/app/(app)/settings/page-ab05dad568b4170e.js","/_next/static/chunks/app/(app)/subscription/page-dc4356b990383766.js","/_next/static/chunks/app/(app)/supplier-records/page-27da7fe677e977b3.js","/_next/static/chunks/app/(app)/users/detail/page-6f88c13a21d8db2e.js","/_next/static/chunks/app/(app)/users/page-b70b53df33b4eae6.js","/_next/static/chunks/app/(app)/website/page-d49e242ddd910eb2.js","/_next/static/chunks/app/(marketing)/compare/[slug]/page-ae620e21d641fcd1.js","/_next/static/chunks/app/(marketing)/en/compare/[slug]/page-3e6e73645f5af019.js","/_next/static/chunks/app/(marketing)/en/guides/[slug]/page-6bc30a3fc83e13d4.js","/_next/static/chunks/app/(marketing)/en/guides/page-94cd4d8428b28b4b.js","/_next/static/chunks/app/(marketing)/en/layout-1b3d95cfed8c2307.js","/_next/static/chunks/app/(marketing)/en/page-83f1934ced5dee35.js","/_next/static/chunks/app/(marketing)/en/pricing/layout-1b3d95cfed8c2307.js","/_next/static/chunks/app/(marketing)/en/pricing/page-8f9a4fcaafcc5c00.js","/_next/static/chunks/app/(marketing)/en/product/layout-1b3d95cfed8c2307.js","/_next/static/chunks/app/(marketing)/en/product/page-2d16d2f43dee15ff.js","/_next/static/chunks/app/(marketing)/en/register/layout-1b3d95cfed8c2307.js","/_next/static/chunks/app/(marketing)/en/register/page-ccd4cd38da938d59.js","/_next/static/chunks/app/(marketing)/en/solutions/[slug]/page-b0bdf25f15cbf289.js","/_next/static/chunks/app/(marketing)/en/solutions/page-7bd7e8f3d48429d5.js","/_next/static/chunks/app/(marketing)/guides/[slug]/page-7fae2ebdaa508c5e.js","/_next/static/chunks/app/(marketing)/guides/page-edb4fdcec1c87fdf.js","/_next/static/chunks/app/(marketing)/layout-1b3d95cfed8c2307.js","/_next/static/chunks/app/(marketing)/page-71b40d54f9d11853.js","/_next/static/chunks/app/(marketing)/pricing/layout-1b3d95cfed8c2307.js","/_next/static/chunks/app/(marketing)/pricing/page-79e163d156f9a8ec.js","/_next/static/chunks/app/(marketing)/product/layout-1b3d95cfed8c2307.js","/_next/static/chunks/app/(marketing)/product/page-67fdd0161ae8f747.js","/_next/static/chunks/app/(marketing)/register/layout-1b3d95cfed8c2307.js","/_next/static/chunks/app/(marketing)/register/page-c562a4dd349bf1b8.js","/_next/static/chunks/app/(marketing)/solutions/[slug]/page-d73def7f50936cec.js","/_next/static/chunks/app/(marketing)/solutions/page-b03eac2ccbe98dad.js","/_next/static/chunks/app/_not-found/page-553fe77d624fa86d.js","/_next/static/chunks/app/activate-owner/layout-1b3d95cfed8c2307.js","/_next/static/chunks/app/activate-owner/page-ed8706b8dedc5fce.js","/_next/static/chunks/app/layout-5cf457ddc5687537.js","/_next/static/chunks/app/login/layout-1b3d95cfed8c2307.js","/_next/static/chunks/app/login/page-7f0fda2cba028a78.js","/_next/static/chunks/app/robots.txt/route-1b3d95cfed8c2307.js","/_next/static/chunks/app/sitemap.xml/route-1b3d95cfed8c2307.js","/_next/static/chunks/framework-94e2e8b8287e5864.js","/_next/static/chunks/main-app-fdc0ff3e9e0bb298.js","/_next/static/chunks/main-bd5f8c4e96cb4993.js","/_next/static/chunks/pages/_app-c0bce1157dc507be.js","/_next/static/chunks/pages/_error-fab33d026d949524.js","/_next/static/chunks/polyfills-42372ed130431b0a.js","/_next/static/chunks/webpack-d36e46cb633b9a13.js","/_next/static/css/e3ae69139b0f41db.css","/_next/static/media/011e180705008d6f-s.woff2","/_next/static/media/01f0c602c274ea55-s.woff2","/_next/static/media/19cfc7226ec3afaa-s.woff2","/_next/static/media/1ebb550cd0a67fc6-s.p.woff2","/_next/static/media/21350d82a1f187e9-s.woff2","/_next/static/media/350b852752f8489d-s.p.woff2","/_next/static/media/3dc379dc9b5dec12-s.p.woff2","/_next/static/media/58f386aa6b1a2a92-s.woff2","/_next/static/media/5ec84f17416dda4d-s.woff2","/_next/static/media/63a79a6cf340c5d2-s.p.woff2","/_next/static/media/7ba5fb2a8c88521c-s.woff2","/_next/static/media/8e9860b6e62d6359-s.woff2","/_next/static/media/92eeb95d069020cc-s.woff2","/_next/static/media/98e207f02528a563-s.p.woff2","/_next/static/media/99dcf268bda04fe5-s.woff2","/_next/static/media/ba9851c3c22cd980-s.woff2","/_next/static/media/c5f10e9e72d35c52-s.woff2","/_next/static/media/c5fe6dc8356a8c31-s.woff2","/_next/static/media/ce401babc0566bc1-s.woff2","/_next/static/media/d29838c109ef09b4-s.woff2","/_next/static/media/d3ebbfd689654d3a-s.p.woff2","/_next/static/media/dd994fbf464986f0-s.p.woff2","/_next/static/media/df0a9ae256c0569c-s.woff2","/_next/static/media/e40af3453d7c920a-s.woff2","/_next/static/media/e4af272ccee01ff0-s.p.woff2","/_next/static/media/e97026df054cf2a3-s.woff2","/_next/static/media/ef4d5661765d0e49-s.woff2","/_next/static/media/f15f45d13243c643-s.woff2","/_next/static/utFn4T7XXIrGit8bUdMrh/_buildManifest.js","/_next/static/utFn4T7XXIrGit8bUdMrh/_ssgManifest.js","/icons/apple-touch-icon.png","/icons/icon-192.png","/icons/icon-512.png","/icons/icon-maskable-192.png","/icons/icon-maskable-512.png","/manifest.webmanifest"];
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
