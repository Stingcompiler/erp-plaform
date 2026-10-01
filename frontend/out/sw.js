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
const BUILD = "30ymOlp5YD-lpP9uxOFom";
const CACHE = `vezano-shell-${BUILD}`;
// Every screen of the app, so the person lands on the page they asked for
// with no network — never on a different one. Filled in at build time from
// the export; the list below is the floor the PWA manifest relies on.
const PRECACHE_PAGES = ["/", "/login/", "/dashboard/", "/sales/", "/inventory/", "/returns/"];
const PRECACHE_APP_PAGES = ["/activate-owner/","/crm/","/customer-records/","/dashboard/","/debts/","/finance/","/forgot-password/","/hr/","/inventory/","/labels/","/login/","/logs/","/org/","/platform-activity/","/platform-analytics/","/platform-companies/","/platform-errors/","/platform-finance/","/platform-leads/","/platform-plans/","/platform-registrations/","/platform-seo/","/platform-subscriptions/","/platform-team/","/platform-team/member/","/platform/","/purchasing/","/reports/","/reset-password/","/returns/","/sales/","/settings/","/subscription/","/supplier-records/","/track/","/users/","/users/detail/","/web-orders/","/website/"];
// Every hashed chunk, stylesheet and font of this build, plus the manifest
// and icons — filled in at build time from the export.
const PRECACHE_ASSETS = ["/_next/static/30ymOlp5YD-lpP9uxOFom/_buildManifest.js","/_next/static/30ymOlp5YD-lpP9uxOFom/_ssgManifest.js","/_next/static/chunks/1147-39be5dae2e80457e.js","/_next/static/chunks/1328-53adf64957863e53.js","/_next/static/chunks/1391-0b93ee9d9f7c21e5.js","/_next/static/chunks/1409-b3ce6e6affad694c.js","/_next/static/chunks/1698-66865647035d1996.js","/_next/static/chunks/182-f26e88b724bd5e6e.js","/_next/static/chunks/2126-608b0a9051caf73e.js","/_next/static/chunks/2785-31913625a873f56c.js","/_next/static/chunks/2900-6389ebc776f71036.js","/_next/static/chunks/3117-61a68afb919b8d59.js","/_next/static/chunks/3233-0feb82df35496bf7.js","/_next/static/chunks/3360-251cb8182434c64c.js","/_next/static/chunks/3415-90a951f20ba5a815.js","/_next/static/chunks/3995-193cf33b08e91925.js","/_next/static/chunks/40b91c18-03576e02c01e0947.js","/_next/static/chunks/4265-18d9d407228d88b9.js","/_next/static/chunks/4462.0f420d4f6374ab9b.js","/_next/static/chunks/4552-0cca2dba36c49832.js","/_next/static/chunks/476-e56912d8c7544d56.js","/_next/static/chunks/4838-398c296d08c00313.js","/_next/static/chunks/5405.a2853eec62072dae.js","/_next/static/chunks/5410-087bc64c21c04d17.js","/_next/static/chunks/5811-c5306e37bd205f86.js","/_next/static/chunks/6702-becc1926d1626e66.js","/_next/static/chunks/689-a0465b186118c2fe.js","/_next/static/chunks/694-73d22f93c292b472.js","/_next/static/chunks/7089-af84b523904bfac2.js","/_next/static/chunks/717-1b6cb7a574f31a0e.js","/_next/static/chunks/7535-20577c64ca0d6cfa.js","/_next/static/chunks/7536-15fbefc9cc695446.js","/_next/static/chunks/7769-313f6fad97c64c58.js","/_next/static/chunks/7941-858e5f9da605dd72.js","/_next/static/chunks/8199-b7822f9e69122fc5.js","/_next/static/chunks/8288-1bb4dbcffa7aee6f.js","/_next/static/chunks/8430-f929184bb61c728a.js","/_next/static/chunks/8557.bdee3fe4b34fcf91.js","/_next/static/chunks/8690-c9c7775750cdbada.js","/_next/static/chunks/8890-93390470aa87db92.js","/_next/static/chunks/9242-5dadef187f312ae1.js","/_next/static/chunks/9535-13712210b96ba167.js","/_next/static/chunks/9865-993a8f72dbe829c9.js","/_next/static/chunks/app/(app)/crm/page-d0358bab9884c461.js","/_next/static/chunks/app/(app)/customer-records/page-17211fb9012ed4e3.js","/_next/static/chunks/app/(app)/dashboard/page-360e271725634dcb.js","/_next/static/chunks/app/(app)/debts/page-eac4c411e164dd33.js","/_next/static/chunks/app/(app)/finance/page-d326f19b331743ca.js","/_next/static/chunks/app/(app)/hr/page-8724398eceb9541b.js","/_next/static/chunks/app/(app)/inventory/page-a5279dd1a67d82f0.js","/_next/static/chunks/app/(app)/labels/page-58b740c1f27e6b7e.js","/_next/static/chunks/app/(app)/layout-1df321fa596872e6.js","/_next/static/chunks/app/(app)/logs/page-881772d0d096d1e8.js","/_next/static/chunks/app/(app)/org/page-418f667ac2edd170.js","/_next/static/chunks/app/(app)/platform-activity/page-4112b65cc599af3f.js","/_next/static/chunks/app/(app)/platform-analytics/page-092497db8b673504.js","/_next/static/chunks/app/(app)/platform-companies/page-e3f03c440dea8607.js","/_next/static/chunks/app/(app)/platform-errors/page-364a308fe3f96a66.js","/_next/static/chunks/app/(app)/platform-finance/page-d9d05306467436a6.js","/_next/static/chunks/app/(app)/platform-leads/page-2919aac25d0f4b91.js","/_next/static/chunks/app/(app)/platform-plans/page-b9d6a6cd6d01c235.js","/_next/static/chunks/app/(app)/platform-registrations/page-ffd92f46a7f4fba2.js","/_next/static/chunks/app/(app)/platform-seo/page-699029aac9009a20.js","/_next/static/chunks/app/(app)/platform-subscriptions/page-aad2e2bdb5e3d70a.js","/_next/static/chunks/app/(app)/platform-team/member/page-67e8d7560ebcfa40.js","/_next/static/chunks/app/(app)/platform-team/page-3c5245ac9efac88a.js","/_next/static/chunks/app/(app)/platform/page-39675366550f52f0.js","/_next/static/chunks/app/(app)/purchasing/page-58bbea269ec0326d.js","/_next/static/chunks/app/(app)/reports/page-bef91e36d8476d76.js","/_next/static/chunks/app/(app)/returns/page-d178d5ac6dff8168.js","/_next/static/chunks/app/(app)/sales/page-b59c79c29aeec2a7.js","/_next/static/chunks/app/(app)/settings/page-b081b7b100645471.js","/_next/static/chunks/app/(app)/subscription/page-43f1f8ac371f578d.js","/_next/static/chunks/app/(app)/supplier-records/page-d39c001669ed0ae9.js","/_next/static/chunks/app/(app)/users/detail/page-6f004c66a6d22379.js","/_next/static/chunks/app/(app)/users/page-dce84aba89c77983.js","/_next/static/chunks/app/(app)/web-orders/page-9df552cf3cc2423b.js","/_next/static/chunks/app/(app)/website/page-9eb3c6304609b578.js","/_next/static/chunks/app/(marketing)/compare/[slug]/page-ccfa92d7d7b5fb18.js","/_next/static/chunks/app/(marketing)/en/compare/[slug]/page-adfdd8929f4f3a77.js","/_next/static/chunks/app/(marketing)/en/guides/[slug]/page-0d89100f4b77a3df.js","/_next/static/chunks/app/(marketing)/en/guides/page-c20a9c71b622eba6.js","/_next/static/chunks/app/(marketing)/en/layout-ddaba7143b3b003d.js","/_next/static/chunks/app/(marketing)/en/page-0284b070f1cdb2f3.js","/_next/static/chunks/app/(marketing)/en/pricing/layout-ddaba7143b3b003d.js","/_next/static/chunks/app/(marketing)/en/pricing/page-3dc60a0678592a37.js","/_next/static/chunks/app/(marketing)/en/product/layout-ddaba7143b3b003d.js","/_next/static/chunks/app/(marketing)/en/product/page-3eaf58984e99e08d.js","/_next/static/chunks/app/(marketing)/en/register/hosting/layout-ddaba7143b3b003d.js","/_next/static/chunks/app/(marketing)/en/register/hosting/page-f5c4be04055af8d1.js","/_next/static/chunks/app/(marketing)/en/register/layout-ddaba7143b3b003d.js","/_next/static/chunks/app/(marketing)/en/register/page-557b8228d2392288.js","/_next/static/chunks/app/(marketing)/en/solutions/[slug]/page-9314aa1809ed89fd.js","/_next/static/chunks/app/(marketing)/en/solutions/page-a51c8f911cc14620.js","/_next/static/chunks/app/(marketing)/en/track/layout-ddaba7143b3b003d.js","/_next/static/chunks/app/(marketing)/en/track/page-f6c1c24f794530a5.js","/_next/static/chunks/app/(marketing)/guides/[slug]/page-d6c57317efe6a243.js","/_next/static/chunks/app/(marketing)/guides/page-c2d1fa1e65bae4c9.js","/_next/static/chunks/app/(marketing)/layout-9f1d1ac1cd125ba6.js","/_next/static/chunks/app/(marketing)/page-72bec7136866f5ca.js","/_next/static/chunks/app/(marketing)/pricing/layout-ddaba7143b3b003d.js","/_next/static/chunks/app/(marketing)/pricing/page-d1bd93d61bc8ea6c.js","/_next/static/chunks/app/(marketing)/product/layout-ddaba7143b3b003d.js","/_next/static/chunks/app/(marketing)/product/page-e4d8f9c119eea031.js","/_next/static/chunks/app/(marketing)/register/hosting/layout-ddaba7143b3b003d.js","/_next/static/chunks/app/(marketing)/register/hosting/page-bf662c4c185edf5e.js","/_next/static/chunks/app/(marketing)/register/layout-ddaba7143b3b003d.js","/_next/static/chunks/app/(marketing)/register/page-c5f4c57d4a19adeb.js","/_next/static/chunks/app/(marketing)/solutions/[slug]/page-1b44dd4bb5ed0aaf.js","/_next/static/chunks/app/(marketing)/solutions/page-6131597c1e5cc3a3.js","/_next/static/chunks/app/(marketing)/track/layout-ddaba7143b3b003d.js","/_next/static/chunks/app/(marketing)/track/page-25aa5f367a05743a.js","/_next/static/chunks/app/_not-found/page-93f5ecd9b5a1b8d5.js","/_next/static/chunks/app/activate-owner/layout-54e434bcc6863f92.js","/_next/static/chunks/app/activate-owner/page-6bfd53ef6caef7e3.js","/_next/static/chunks/app/forgot-password/layout-54e434bcc6863f92.js","/_next/static/chunks/app/forgot-password/page-650b79d7724c0183.js","/_next/static/chunks/app/layout-0cb366ae51107602.js","/_next/static/chunks/app/login/layout-54e434bcc6863f92.js","/_next/static/chunks/app/login/page-034ec86c56b9c0fe.js","/_next/static/chunks/app/reset-password/layout-54e434bcc6863f92.js","/_next/static/chunks/app/reset-password/page-04cb2c4ffbbd91fb.js","/_next/static/chunks/app/robots.txt/route-ddaba7143b3b003d.js","/_next/static/chunks/app/sitemap.xml/route-ddaba7143b3b003d.js","/_next/static/chunks/framework-ac871cde7d705c3a.js","/_next/static/chunks/main-61969269e7b3dad5.js","/_next/static/chunks/main-app-d3c2614b980cfab3.js","/_next/static/chunks/pages/_app-c0e3f7ff6ef43cb0.js","/_next/static/chunks/pages/_error-6bf3d2bf6fe2d033.js","/_next/static/chunks/polyfills-42372ed130431b0a.js","/_next/static/chunks/webpack-8d30648690922841.js","/_next/static/css/77fdca18a18c7e83.css","/_next/static/css/8a5a4fa230ce7eed.css","/_next/static/media/011e180705008d6f.woff2","/_next/static/media/19cfc7226ec3afaa.woff2","/_next/static/media/1ebb550cd0a67fc6.p.woff2","/_next/static/media/21350d82a1f187e9.woff2","/_next/static/media/3dc379dc9b5dec12.p.woff2","/_next/static/media/58c726479f69cacd.woff2","/_next/static/media/58f386aa6b1a2a92.woff2","/_next/static/media/63a79a6cf340c5d2.p.woff2","/_next/static/media/7ba5fb2a8c88521c.woff2","/_next/static/media/8e9860b6e62d6359.woff2","/_next/static/media/92eeb95d069020cc.woff2","/_next/static/media/98e207f02528a563.p.woff2","/_next/static/media/99dcf268bda04fe5.woff2","/_next/static/media/ba9851c3c22cd980.woff2","/_next/static/media/bd9c8c62ffadd9dd.p.woff2","/_next/static/media/c5f10e9e72d35c52.woff2","/_next/static/media/c5fe6dc8356a8c31.woff2","/_next/static/media/cc8b755e9c1ba115.woff2","/_next/static/media/ce401babc0566bc1.woff2","/_next/static/media/d29838c109ef09b4.woff2","/_next/static/media/d3ebbfd689654d3a.p.woff2","/_next/static/media/dd994fbf464986f0.p.woff2","/_next/static/media/df0a9ae256c0569c.woff2","/_next/static/media/e40af3453d7c920a.woff2","/_next/static/media/e4af272ccee01ff0.p.woff2","/_next/static/media/e97026df054cf2a3.woff2","/_next/static/media/ef4d5661765d0e49.woff2","/_next/static/media/f15f45d13243c643.woff2","/_next/static/media/f952393b67d608ec.p.woff2","/icons/apple-touch-icon.png","/icons/badge-96.png","/icons/icon-192.png","/icons/icon-512.png","/icons/icon-maskable-192.png","/icons/icon-maskable-512.png","/manifest.webmanifest"];
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
  try { data = event.data ? event.data.json() : {}; } catch { data = { title: "Vezano Pro", body: event.data?.text() || "" }; }
  event.waitUntil(
    self.registration.showNotification(data.title || "Vezano Pro", {
      body: data.body || "",
      icon: "/icons/icon-192.png",
      badge: "/icons/badge-96.png",
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
      "<!doctype html><meta charset=utf-8><title>Vezano Pro</title>" +
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
