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
const BUILD = "j1YQldavroraqbp9UfNS8";
const CACHE = `vezano-shell-${BUILD}`;
// Every screen of the app, so the person lands on the page they asked for
// with no network — never on a different one. Filled in at build time from
// the export; the list below is the floor the PWA manifest relies on.
const PRECACHE_PAGES = ["/", "/login/", "/dashboard/", "/sales/", "/inventory/", "/returns/"];
const PRECACHE_APP_PAGES = ["/activate-owner/","/crm/","/customer-records/","/dashboard/","/debts/","/finance/","/forgot-password/","/hr/","/inventory/","/labels/","/login/","/logs/","/org/","/platform-activity/","/platform-analytics/","/platform-companies/","/platform-errors/","/platform-finance/","/platform-leads/","/platform-plans/","/platform-registrations/","/platform-seo/","/platform-subscriptions/","/platform-team/","/platform-team/member/","/platform/","/purchasing/","/reports/","/reset-password/","/returns/","/sales/","/settings/","/subscription/","/supplier-records/","/users/","/users/detail/","/web-orders/","/website/"];
// Every hashed chunk, stylesheet and font of this build, plus the manifest
// and icons — filled in at build time from the export.
const PRECACHE_ASSETS = ["/_next/static/chunks/1020-6f1ebf6897f8a2a9.js","/_next/static/chunks/14-15789058ca424700.js","/_next/static/chunks/2017-2b5a50fa5ca16968.js","/_next/static/chunks/2218-d514cff52506fbad.js","/_next/static/chunks/2549-095286aa79aa569c.js","/_next/static/chunks/2841.86f35ccd294715ef.js","/_next/static/chunks/3569-0a151bf8ea9af3f4.js","/_next/static/chunks/3922-44254cb46b81fb04.js","/_next/static/chunks/4352-260b92b6ae205a56.js","/_next/static/chunks/4877-12c785569bbb43b7.js","/_next/static/chunks/5024-50a836c1f87eb7c6.js","/_next/static/chunks/5258-8fa9e6c5f163d143.js","/_next/static/chunks/5291-65d0861ad6899788.js","/_next/static/chunks/5308-cab963b28151265f.js","/_next/static/chunks/5949-1418c3efaba319d1.js","/_next/static/chunks/5959-2a566bc00a7f1db5.js","/_next/static/chunks/7069-7f85b156a990a93f.js","/_next/static/chunks/719-662217eb3165b1b3.js","/_next/static/chunks/7359-1e065d57b3d3c640.js","/_next/static/chunks/7566-5fae5d85a95b5737.js","/_next/static/chunks/802-21edc8cac76b8de7.js","/_next/static/chunks/8039-3e0a5d7f4a3c40e8.js","/_next/static/chunks/8170-3b2073dea992214d.js","/_next/static/chunks/8558-ef7a7c56ea3ae526.js","/_next/static/chunks/8605-50879c729dfd959b.js","/_next/static/chunks/8671-d8a18e6f862682c4.js","/_next/static/chunks/9272-f9f3d4b4bf78f0b1.js","/_next/static/chunks/9301-0e619f79735e3c18.js","/_next/static/chunks/9899-18dcf26cdd2226c6.js","/_next/static/chunks/app/(app)/crm/page-ba0b397725d444e2.js","/_next/static/chunks/app/(app)/customer-records/page-6698772c8c35a23a.js","/_next/static/chunks/app/(app)/dashboard/page-455c507ca8ff00c4.js","/_next/static/chunks/app/(app)/debts/page-0ac55a9cb8b58547.js","/_next/static/chunks/app/(app)/finance/page-01addfb9a51daf58.js","/_next/static/chunks/app/(app)/hr/page-e735e4152a3844fd.js","/_next/static/chunks/app/(app)/inventory/page-9aefc825ac9e4627.js","/_next/static/chunks/app/(app)/labels/page-531a9457d700719e.js","/_next/static/chunks/app/(app)/layout-ac9ba29fdf400ef5.js","/_next/static/chunks/app/(app)/logs/page-1e927bfe220671a7.js","/_next/static/chunks/app/(app)/org/page-5820509ede171ca0.js","/_next/static/chunks/app/(app)/platform-activity/page-e5c2185f81245dfd.js","/_next/static/chunks/app/(app)/platform-analytics/page-764aa785b27b4dc4.js","/_next/static/chunks/app/(app)/platform-companies/page-d9ecaf6b16ed119b.js","/_next/static/chunks/app/(app)/platform-errors/page-b44582c85d4de80f.js","/_next/static/chunks/app/(app)/platform-finance/page-e0b81fde364909a3.js","/_next/static/chunks/app/(app)/platform-leads/page-e86cff68f13e68ca.js","/_next/static/chunks/app/(app)/platform-plans/page-c02512ddb6c72a93.js","/_next/static/chunks/app/(app)/platform-registrations/page-070c8f4d17cbdbed.js","/_next/static/chunks/app/(app)/platform-seo/page-d8b35b970e04ac38.js","/_next/static/chunks/app/(app)/platform-subscriptions/page-d4102c75b2ef73a2.js","/_next/static/chunks/app/(app)/platform-team/member/page-a06d6c1e5916c4c2.js","/_next/static/chunks/app/(app)/platform-team/page-debff090ef46c9e2.js","/_next/static/chunks/app/(app)/platform/page-26034ce02e397939.js","/_next/static/chunks/app/(app)/purchasing/page-cb66c74a24cabf30.js","/_next/static/chunks/app/(app)/reports/page-56379ed1a588b0c1.js","/_next/static/chunks/app/(app)/returns/page-58c5f26d7f9c5bfd.js","/_next/static/chunks/app/(app)/sales/page-01db8ccc0ce002c4.js","/_next/static/chunks/app/(app)/settings/page-25a5db470f802e1b.js","/_next/static/chunks/app/(app)/subscription/page-723587885d279f86.js","/_next/static/chunks/app/(app)/supplier-records/page-adfd0611e226da80.js","/_next/static/chunks/app/(app)/users/detail/page-49153fbdb3bfadbd.js","/_next/static/chunks/app/(app)/users/page-e4a07c86c525120b.js","/_next/static/chunks/app/(app)/web-orders/page-aaff8d76187ad7a5.js","/_next/static/chunks/app/(app)/website/page-ad0587fd9d89b2f1.js","/_next/static/chunks/app/(marketing)/compare/[slug]/page-37e7f4b9157b2bce.js","/_next/static/chunks/app/(marketing)/en/compare/[slug]/page-2b471ce288c48ce1.js","/_next/static/chunks/app/(marketing)/en/guides/[slug]/page-7123b738a7e1ae1e.js","/_next/static/chunks/app/(marketing)/en/guides/page-1717a45d7d327300.js","/_next/static/chunks/app/(marketing)/en/layout-bba71f66b30630d4.js","/_next/static/chunks/app/(marketing)/en/page-66bd03be558cbddc.js","/_next/static/chunks/app/(marketing)/en/pricing/layout-bba71f66b30630d4.js","/_next/static/chunks/app/(marketing)/en/pricing/page-59576b132522d5a5.js","/_next/static/chunks/app/(marketing)/en/product/layout-bba71f66b30630d4.js","/_next/static/chunks/app/(marketing)/en/product/page-e959b832b8bb2c40.js","/_next/static/chunks/app/(marketing)/en/register/hosting/layout-bba71f66b30630d4.js","/_next/static/chunks/app/(marketing)/en/register/hosting/page-da4d79dab97c3569.js","/_next/static/chunks/app/(marketing)/en/register/layout-bba71f66b30630d4.js","/_next/static/chunks/app/(marketing)/en/register/page-460a3a9fd6cd2aef.js","/_next/static/chunks/app/(marketing)/en/solutions/[slug]/page-d9031cf67d2500dd.js","/_next/static/chunks/app/(marketing)/en/solutions/page-9b4b45b44354b15d.js","/_next/static/chunks/app/(marketing)/guides/[slug]/page-2391bfc724a0376d.js","/_next/static/chunks/app/(marketing)/guides/page-1dd7bd3561f6280e.js","/_next/static/chunks/app/(marketing)/layout-bba71f66b30630d4.js","/_next/static/chunks/app/(marketing)/page-05a95e7c306b7240.js","/_next/static/chunks/app/(marketing)/pricing/layout-bba71f66b30630d4.js","/_next/static/chunks/app/(marketing)/pricing/page-af7ada95f14eb4bf.js","/_next/static/chunks/app/(marketing)/product/layout-bba71f66b30630d4.js","/_next/static/chunks/app/(marketing)/product/page-a44920ed0d1c7915.js","/_next/static/chunks/app/(marketing)/register/hosting/layout-bba71f66b30630d4.js","/_next/static/chunks/app/(marketing)/register/hosting/page-7c783d6c1dca7f94.js","/_next/static/chunks/app/(marketing)/register/layout-bba71f66b30630d4.js","/_next/static/chunks/app/(marketing)/register/page-5318342bd658a8eb.js","/_next/static/chunks/app/(marketing)/solutions/[slug]/page-4da48a577aac5a0b.js","/_next/static/chunks/app/(marketing)/solutions/page-4429962b702f8aa3.js","/_next/static/chunks/app/_not-found/page-68a0584aa6a8d18f.js","/_next/static/chunks/app/activate-owner/layout-bba71f66b30630d4.js","/_next/static/chunks/app/activate-owner/page-e007fe5638c28105.js","/_next/static/chunks/app/forgot-password/layout-bba71f66b30630d4.js","/_next/static/chunks/app/forgot-password/page-f809bdd89c4dcd50.js","/_next/static/chunks/app/layout-62da2e722dbafe60.js","/_next/static/chunks/app/login/layout-bba71f66b30630d4.js","/_next/static/chunks/app/login/page-225e86c4d0932254.js","/_next/static/chunks/app/reset-password/layout-bba71f66b30630d4.js","/_next/static/chunks/app/reset-password/page-fa7bef5ca62d0d0a.js","/_next/static/chunks/app/robots.txt/route-bba71f66b30630d4.js","/_next/static/chunks/app/sitemap.xml/route-bba71f66b30630d4.js","/_next/static/chunks/e46ef968-b68f361a13319b06.js","/_next/static/chunks/framework-e856097ae3f00b5b.js","/_next/static/chunks/main-161e8115e5182cdb.js","/_next/static/chunks/main-app-3877a70d26e4c09e.js","/_next/static/chunks/pages/_app-d0a68f56507e1d03.js","/_next/static/chunks/pages/_error-87b7d7c4dcd46628.js","/_next/static/chunks/polyfills-42372ed130431b0a.js","/_next/static/chunks/webpack-2375102e4c95a2c5.js","/_next/static/css/7d876e664442c41a.css","/_next/static/j1YQldavroraqbp9UfNS8/_buildManifest.js","/_next/static/j1YQldavroraqbp9UfNS8/_ssgManifest.js","/_next/static/media/011e180705008d6f-s.woff2","/_next/static/media/01f0c602c274ea55-s.woff2","/_next/static/media/19cfc7226ec3afaa-s.woff2","/_next/static/media/1ebb550cd0a67fc6-s.p.woff2","/_next/static/media/21350d82a1f187e9-s.woff2","/_next/static/media/350b852752f8489d-s.p.woff2","/_next/static/media/3dc379dc9b5dec12-s.p.woff2","/_next/static/media/58f386aa6b1a2a92-s.woff2","/_next/static/media/5ec84f17416dda4d-s.woff2","/_next/static/media/63a79a6cf340c5d2-s.p.woff2","/_next/static/media/7ba5fb2a8c88521c-s.woff2","/_next/static/media/8e9860b6e62d6359-s.woff2","/_next/static/media/92eeb95d069020cc-s.woff2","/_next/static/media/98e207f02528a563-s.p.woff2","/_next/static/media/99dcf268bda04fe5-s.woff2","/_next/static/media/ba9851c3c22cd980-s.woff2","/_next/static/media/c5f10e9e72d35c52-s.woff2","/_next/static/media/c5fe6dc8356a8c31-s.woff2","/_next/static/media/ce401babc0566bc1-s.woff2","/_next/static/media/d29838c109ef09b4-s.woff2","/_next/static/media/d3ebbfd689654d3a-s.p.woff2","/_next/static/media/dd994fbf464986f0-s.p.woff2","/_next/static/media/df0a9ae256c0569c-s.woff2","/_next/static/media/e40af3453d7c920a-s.woff2","/_next/static/media/e4af272ccee01ff0-s.p.woff2","/_next/static/media/e97026df054cf2a3-s.woff2","/_next/static/media/ef4d5661765d0e49-s.woff2","/_next/static/media/f15f45d13243c643-s.woff2","/icons/apple-touch-icon.png","/icons/icon-192.png","/icons/icon-512.png","/icons/icon-maskable-192.png","/icons/icon-maskable-512.png","/manifest.webmanifest"];
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

// Web Push from the server (core/push.py): a new order for this shop. The
// payload is small and self-contained; tapping opens the order.
self.addEventListener("push", (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch { data = { title: "Vezano", body: event.data?.text() || "" }; }
  event.waitUntil(
    self.registration.showNotification(data.title || "Vezano", {
      body: data.body || "",
      icon: "/icons/icon-192.png",
      badge: "/icons/icon-192.png",
      tag: data.tag || undefined,
      renotify: Boolean(data.tag),
      data: { url: data.url || "/web-orders/" },
      dir: "auto",
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL(event.notification.data?.url || "/web-orders/", self.location.origin).href;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
      const open = list.find((c) => "focus" in c);
      if (open) { open.navigate(url); return open.focus(); }
      return self.clients.openWindow(url);
    })
  );
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
