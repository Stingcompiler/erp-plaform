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
const BUILD = "PMzFA--7hUjLUHrZn0iXf";
const CACHE = `vezano-shell-${BUILD}`;
// Every screen of the app, so the person lands on the page they asked for
// with no network — never on a different one. Filled in at build time from
// the export; the list below is the floor the PWA manifest relies on.
const PRECACHE_PAGES = ["/", "/login/", "/dashboard/", "/sales/", "/inventory/", "/returns/"];
const PRECACHE_APP_PAGES = ["/activate-owner/","/crm/","/customer-records/","/dashboard/","/debts/","/finance/","/forgot-password/","/hr/","/inventory/","/labels/","/login/","/logs/","/org/","/platform-activity/","/platform-analytics/","/platform-companies/","/platform-errors/","/platform-finance/","/platform-leads/","/platform-plans/","/platform-registrations/","/platform-seo/","/platform-subscriptions/","/platform-team/","/platform-team/member/","/platform/","/purchasing/","/reports/","/reset-password/","/returns/","/sales/","/settings/","/subscription/","/supplier-records/","/track/","/users/","/users/detail/","/web-orders/","/website/"];
// Every hashed chunk, stylesheet and font of this build, plus the manifest
// and icons — filled in at build time from the export.
const PRECACHE_ASSETS = ["/_next/static/PMzFA--7hUjLUHrZn0iXf/_buildManifest.js","/_next/static/PMzFA--7hUjLUHrZn0iXf/_ssgManifest.js","/_next/static/chunks/1328-f61aca8e87377237.js","/_next/static/chunks/1391-0b93ee9d9f7c21e5.js","/_next/static/chunks/2126-44e0a7b8c7fcb4eb.js","/_next/static/chunks/2395-f405d986edddf4c1.js","/_next/static/chunks/2901-a56b24b242fd6398.js","/_next/static/chunks/2906-02413d83ab7d3b8c.js","/_next/static/chunks/2942-8fee8566988634b0.js","/_next/static/chunks/3415-20b7e72c017ec448.js","/_next/static/chunks/3431-56b9e07e57971d94.js","/_next/static/chunks/3995-193cf33b08e91925.js","/_next/static/chunks/40b91c18-03576e02c01e0947.js","/_next/static/chunks/4200-086e4dd05ced843c.js","/_next/static/chunks/4265-101243f1e4282e78.js","/_next/static/chunks/4353-82f00cb0b3d556b9.js","/_next/static/chunks/4473-8ea572ad178595e9.js","/_next/static/chunks/476-fc85ff3f4740c2ac.js","/_next/static/chunks/4838-398c296d08c00313.js","/_next/static/chunks/5405.a2853eec62072dae.js","/_next/static/chunks/5410-087bc64c21c04d17.js","/_next/static/chunks/6100-1fc6b211fc806fee.js","/_next/static/chunks/6702-5a33da0ccd8afcac.js","/_next/static/chunks/689-8a8ebcacd8accd22.js","/_next/static/chunks/7536-15fbefc9cc695446.js","/_next/static/chunks/7769-313f6fad97c64c58.js","/_next/static/chunks/8117-220f357cdf1dced1.js","/_next/static/chunks/8199-cddeddc9f99c0f79.js","/_next/static/chunks/8430-f929184bb61c728a.js","/_next/static/chunks/8843-ea4e707eb8de8c16.js","/_next/static/chunks/8890-01971f9367d4d1b0.js","/_next/static/chunks/9265-7b58b312cc89db09.js","/_next/static/chunks/9394-b03e7326d8e6febd.js","/_next/static/chunks/9681-f0c3c1351c1d91b8.js","/_next/static/chunks/9865-d844f91f833a30d6.js","/_next/static/chunks/app/(app)/crm/page-d76d7f815c35016f.js","/_next/static/chunks/app/(app)/customer-records/page-320c601f33945c64.js","/_next/static/chunks/app/(app)/dashboard/page-c98bc1d335eb7c29.js","/_next/static/chunks/app/(app)/debts/page-7042c5b004aa031d.js","/_next/static/chunks/app/(app)/finance/page-e7f2e97650f61cf3.js","/_next/static/chunks/app/(app)/hr/page-4a6001208bce3b45.js","/_next/static/chunks/app/(app)/inventory/page-3477875d755febc6.js","/_next/static/chunks/app/(app)/labels/page-bf6b56e0c523c90e.js","/_next/static/chunks/app/(app)/layout-c5cdcf899839aa5c.js","/_next/static/chunks/app/(app)/logs/page-9b80b804a13bd31a.js","/_next/static/chunks/app/(app)/org/page-982e5e0156033516.js","/_next/static/chunks/app/(app)/platform-activity/page-327153187cb3f9d9.js","/_next/static/chunks/app/(app)/platform-analytics/page-0bc1601fba6c23b0.js","/_next/static/chunks/app/(app)/platform-companies/page-906e2c7ed7d04ca9.js","/_next/static/chunks/app/(app)/platform-errors/page-4ee6947cee9f719c.js","/_next/static/chunks/app/(app)/platform-finance/page-a22a0bbf578cc3b4.js","/_next/static/chunks/app/(app)/platform-leads/page-f8c1e9be73e5dfe6.js","/_next/static/chunks/app/(app)/platform-plans/page-19ba1b53e33669e8.js","/_next/static/chunks/app/(app)/platform-registrations/page-300fd75111cc3bc0.js","/_next/static/chunks/app/(app)/platform-seo/page-c4966f4ba2e598e2.js","/_next/static/chunks/app/(app)/platform-subscriptions/page-34f55f304342a806.js","/_next/static/chunks/app/(app)/platform-team/member/page-9779222352d91c3f.js","/_next/static/chunks/app/(app)/platform-team/page-1726f4a46586ca31.js","/_next/static/chunks/app/(app)/platform/page-689eb78264fbbdd5.js","/_next/static/chunks/app/(app)/purchasing/page-2de481c56c512032.js","/_next/static/chunks/app/(app)/reports/page-daa6d60683f24c9b.js","/_next/static/chunks/app/(app)/returns/page-3a7d8e3f591584ee.js","/_next/static/chunks/app/(app)/sales/page-751e566141c87d31.js","/_next/static/chunks/app/(app)/settings/page-986dfcd57081337f.js","/_next/static/chunks/app/(app)/subscription/page-fbb5c27b138c6b28.js","/_next/static/chunks/app/(app)/supplier-records/page-233a686d54bfbc06.js","/_next/static/chunks/app/(app)/users/detail/page-e0ce804419ee7a57.js","/_next/static/chunks/app/(app)/users/page-f3b42824bca3ba29.js","/_next/static/chunks/app/(app)/web-orders/page-02f6fbaaa48ac5cf.js","/_next/static/chunks/app/(app)/website/page-c077b586f6ff9b13.js","/_next/static/chunks/app/(marketing)/compare/[slug]/page-76b60bd7e324adc1.js","/_next/static/chunks/app/(marketing)/en/compare/[slug]/page-705da12a2a210ef6.js","/_next/static/chunks/app/(marketing)/en/guides/[slug]/page-3a06a14e07c9eac5.js","/_next/static/chunks/app/(marketing)/en/guides/page-c5f87ab93deba461.js","/_next/static/chunks/app/(marketing)/en/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/en/page-c7c95bf1e6f65c2a.js","/_next/static/chunks/app/(marketing)/en/pricing/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/en/pricing/page-f609464343cc9e49.js","/_next/static/chunks/app/(marketing)/en/product/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/en/product/page-cfaabf23578e0289.js","/_next/static/chunks/app/(marketing)/en/register/hosting/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/en/register/hosting/page-ef9652ed8ee3e314.js","/_next/static/chunks/app/(marketing)/en/register/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/en/register/page-5ca53ddeb12745c1.js","/_next/static/chunks/app/(marketing)/en/solutions/[slug]/page-7373aa7e690b2e64.js","/_next/static/chunks/app/(marketing)/en/solutions/page-e1f17a227db47793.js","/_next/static/chunks/app/(marketing)/en/track/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/en/track/page-5e83797df23a9cb4.js","/_next/static/chunks/app/(marketing)/guides/[slug]/page-b0335e46aa74f17b.js","/_next/static/chunks/app/(marketing)/guides/page-54d18c65147f3f12.js","/_next/static/chunks/app/(marketing)/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/page-e11186bdab0d28fb.js","/_next/static/chunks/app/(marketing)/pricing/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/pricing/page-375ca5f0bc3a37d9.js","/_next/static/chunks/app/(marketing)/product/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/product/page-b6babdf2e011c5e2.js","/_next/static/chunks/app/(marketing)/register/hosting/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/register/hosting/page-5f7f17e0b11d7ab8.js","/_next/static/chunks/app/(marketing)/register/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/register/page-b3d6272dbc1099b3.js","/_next/static/chunks/app/(marketing)/solutions/[slug]/page-ec6202ac1903a87a.js","/_next/static/chunks/app/(marketing)/solutions/page-41bdae7a6fa6f0c4.js","/_next/static/chunks/app/(marketing)/track/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/track/page-24f7d2e5d44bd4c3.js","/_next/static/chunks/app/_not-found/page-93f5ecd9b5a1b8d5.js","/_next/static/chunks/app/activate-owner/layout-9111370ccccd4922.js","/_next/static/chunks/app/activate-owner/page-5a0f768fc3ca02a7.js","/_next/static/chunks/app/forgot-password/layout-9111370ccccd4922.js","/_next/static/chunks/app/forgot-password/page-77ae10fd1053fc53.js","/_next/static/chunks/app/layout-819a1e71149b71ca.js","/_next/static/chunks/app/login/layout-9111370ccccd4922.js","/_next/static/chunks/app/login/page-d0935dc5edafbaa9.js","/_next/static/chunks/app/reset-password/layout-9111370ccccd4922.js","/_next/static/chunks/app/reset-password/page-a7e9d041514ff17a.js","/_next/static/chunks/app/robots.txt/route-9111370ccccd4922.js","/_next/static/chunks/app/sitemap.xml/route-9111370ccccd4922.js","/_next/static/chunks/framework-ac871cde7d705c3a.js","/_next/static/chunks/main-61969269e7b3dad5.js","/_next/static/chunks/main-app-d3c2614b980cfab3.js","/_next/static/chunks/pages/_app-c0e3f7ff6ef43cb0.js","/_next/static/chunks/pages/_error-6bf3d2bf6fe2d033.js","/_next/static/chunks/polyfills-42372ed130431b0a.js","/_next/static/chunks/webpack-91ffaed1d638f79f.js","/_next/static/css/35f0eace0f5cff60.css","/_next/static/media/011e180705008d6f-s.woff2","/_next/static/media/19cfc7226ec3afaa-s.woff2","/_next/static/media/1ebb550cd0a67fc6-s.p.woff2","/_next/static/media/21350d82a1f187e9-s.woff2","/_next/static/media/3dc379dc9b5dec12-s.p.woff2","/_next/static/media/58c726479f69cacd-s.woff2","/_next/static/media/58f386aa6b1a2a92-s.woff2","/_next/static/media/63a79a6cf340c5d2-s.p.woff2","/_next/static/media/7ba5fb2a8c88521c-s.woff2","/_next/static/media/8e9860b6e62d6359-s.woff2","/_next/static/media/92eeb95d069020cc-s.woff2","/_next/static/media/98e207f02528a563-s.p.woff2","/_next/static/media/99dcf268bda04fe5-s.woff2","/_next/static/media/ba9851c3c22cd980-s.woff2","/_next/static/media/bd9c8c62ffadd9dd-s.p.woff2","/_next/static/media/c5f10e9e72d35c52-s.woff2","/_next/static/media/c5fe6dc8356a8c31-s.woff2","/_next/static/media/cc8b755e9c1ba115-s.woff2","/_next/static/media/ce401babc0566bc1-s.woff2","/_next/static/media/d29838c109ef09b4-s.woff2","/_next/static/media/d3ebbfd689654d3a-s.p.woff2","/_next/static/media/dd994fbf464986f0-s.p.woff2","/_next/static/media/df0a9ae256c0569c-s.woff2","/_next/static/media/e40af3453d7c920a-s.woff2","/_next/static/media/e4af272ccee01ff0-s.p.woff2","/_next/static/media/e97026df054cf2a3-s.woff2","/_next/static/media/ef4d5661765d0e49-s.woff2","/_next/static/media/f15f45d13243c643-s.woff2","/_next/static/media/f952393b67d608ec-s.p.woff2","/icons/apple-touch-icon.png","/icons/badge-96.png","/icons/icon-192.png","/icons/icon-512.png","/icons/icon-maskable-192.png","/icons/icon-maskable-512.png","/manifest.webmanifest"];
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
