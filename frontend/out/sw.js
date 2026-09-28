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
const BUILD = "bXqvDE4yHazu-KtbG7ARj";
const CACHE = `vezano-shell-${BUILD}`;
// Every screen of the app, so the person lands on the page they asked for
// with no network — never on a different one. Filled in at build time from
// the export; the list below is the floor the PWA manifest relies on.
const PRECACHE_PAGES = ["/", "/login/", "/dashboard/", "/sales/", "/inventory/", "/returns/"];
const PRECACHE_APP_PAGES = ["/activate-owner/","/crm/","/customer-records/","/dashboard/","/debts/","/finance/","/forgot-password/","/hr/","/inventory/","/labels/","/login/","/logs/","/org/","/platform-activity/","/platform-analytics/","/platform-companies/","/platform-errors/","/platform-finance/","/platform-leads/","/platform-plans/","/platform-registrations/","/platform-seo/","/platform-subscriptions/","/platform-team/","/platform-team/member/","/platform/","/purchasing/","/reports/","/reset-password/","/returns/","/sales/","/settings/","/subscription/","/supplier-records/","/track/","/users/","/users/detail/","/web-orders/","/website/"];
// Every hashed chunk, stylesheet and font of this build, plus the manifest
// and icons — filled in at build time from the export.
const PRECACHE_ASSETS = ["/_next/static/bXqvDE4yHazu-KtbG7ARj/_buildManifest.js","/_next/static/bXqvDE4yHazu-KtbG7ARj/_ssgManifest.js","/_next/static/chunks/1328-f61aca8e87377237.js","/_next/static/chunks/1391-0b93ee9d9f7c21e5.js","/_next/static/chunks/2126-66d72952c3971eda.js","/_next/static/chunks/2395-2840df6565c7c063.js","/_next/static/chunks/2901-88da629a5face03f.js","/_next/static/chunks/2906-7e07ec2edf393ed5.js","/_next/static/chunks/2939-b079abe38d3c6fba.js","/_next/static/chunks/2942-8fee8566988634b0.js","/_next/static/chunks/3415-211d6c178abcb829.js","/_next/static/chunks/3431-86d1e29b5623eaf2.js","/_next/static/chunks/3995-193cf33b08e91925.js","/_next/static/chunks/40b91c18-03576e02c01e0947.js","/_next/static/chunks/4200-086e4dd05ced843c.js","/_next/static/chunks/4265-101243f1e4282e78.js","/_next/static/chunks/4353-82f00cb0b3d556b9.js","/_next/static/chunks/4473-8ea572ad178595e9.js","/_next/static/chunks/476-fc85ff3f4740c2ac.js","/_next/static/chunks/4838-c316258577a956ac.js","/_next/static/chunks/5405.a2853eec62072dae.js","/_next/static/chunks/5410-087bc64c21c04d17.js","/_next/static/chunks/6100-1fc6b211fc806fee.js","/_next/static/chunks/6579-047551cd8b13d2a8.js","/_next/static/chunks/6702-5a33da0ccd8afcac.js","/_next/static/chunks/689-8a8ebcacd8accd22.js","/_next/static/chunks/7536-15fbefc9cc695446.js","/_next/static/chunks/7769-313f6fad97c64c58.js","/_next/static/chunks/8117-220f357cdf1dced1.js","/_next/static/chunks/8430-f929184bb61c728a.js","/_next/static/chunks/8890-01971f9367d4d1b0.js","/_next/static/chunks/9265-7b58b312cc89db09.js","/_next/static/chunks/9394-b03e7326d8e6febd.js","/_next/static/chunks/9681-91b24db0c6ce4433.js","/_next/static/chunks/9865-d844f91f833a30d6.js","/_next/static/chunks/app/(app)/crm/page-71bf99f9fb168bf0.js","/_next/static/chunks/app/(app)/customer-records/page-272f26c079b8b66d.js","/_next/static/chunks/app/(app)/dashboard/page-bd000c7b9ee16fed.js","/_next/static/chunks/app/(app)/debts/page-9321e06a656c2167.js","/_next/static/chunks/app/(app)/finance/page-6c187a5e824a4c58.js","/_next/static/chunks/app/(app)/hr/page-2067436a8d71e7e7.js","/_next/static/chunks/app/(app)/inventory/page-b6b6728d27f99898.js","/_next/static/chunks/app/(app)/labels/page-d727bf73d0104be8.js","/_next/static/chunks/app/(app)/layout-459bccc5e414757d.js","/_next/static/chunks/app/(app)/logs/page-6ceeb6611fd48ad9.js","/_next/static/chunks/app/(app)/org/page-0fb3685fc1294f9e.js","/_next/static/chunks/app/(app)/platform-activity/page-9639d3ed919590ab.js","/_next/static/chunks/app/(app)/platform-analytics/page-e31b4acaca4d836b.js","/_next/static/chunks/app/(app)/platform-companies/page-604641d3a22ea2d2.js","/_next/static/chunks/app/(app)/platform-errors/page-2e7cad129304bb15.js","/_next/static/chunks/app/(app)/platform-finance/page-325b8105bca3d05f.js","/_next/static/chunks/app/(app)/platform-leads/page-c915af87d5e4e030.js","/_next/static/chunks/app/(app)/platform-plans/page-5d44d2ae7c147f26.js","/_next/static/chunks/app/(app)/platform-registrations/page-680fe8f0c746e38c.js","/_next/static/chunks/app/(app)/platform-seo/page-5daf2fb34406335f.js","/_next/static/chunks/app/(app)/platform-subscriptions/page-8c1d16678e9cb480.js","/_next/static/chunks/app/(app)/platform-team/member/page-40b12de048d21b0d.js","/_next/static/chunks/app/(app)/platform-team/page-94728c09c5dd6507.js","/_next/static/chunks/app/(app)/platform/page-175b1ed36595b77a.js","/_next/static/chunks/app/(app)/purchasing/page-0f99e32b99fa2c9b.js","/_next/static/chunks/app/(app)/reports/page-2cb8cdae664b4cbe.js","/_next/static/chunks/app/(app)/returns/page-48f717bf757fb4e0.js","/_next/static/chunks/app/(app)/sales/page-8cf0afc1a300b4e3.js","/_next/static/chunks/app/(app)/settings/page-41e6bba6807954df.js","/_next/static/chunks/app/(app)/subscription/page-d5d76bdf34503891.js","/_next/static/chunks/app/(app)/supplier-records/page-7dcfec2239ab1ee3.js","/_next/static/chunks/app/(app)/users/detail/page-f05a455f707033bf.js","/_next/static/chunks/app/(app)/users/page-d34e0f6e81dfc1fc.js","/_next/static/chunks/app/(app)/web-orders/page-ad792cc823706b0b.js","/_next/static/chunks/app/(app)/website/page-91c6a31f91b18478.js","/_next/static/chunks/app/(marketing)/compare/[slug]/page-482b12a989405a70.js","/_next/static/chunks/app/(marketing)/en/compare/[slug]/page-fbb75b19bf664ae0.js","/_next/static/chunks/app/(marketing)/en/guides/[slug]/page-fd4f9c91e012bde7.js","/_next/static/chunks/app/(marketing)/en/guides/page-1774e8045476fd2a.js","/_next/static/chunks/app/(marketing)/en/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/en/page-58436622db4943db.js","/_next/static/chunks/app/(marketing)/en/pricing/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/en/pricing/page-ed1f8bd9006155fa.js","/_next/static/chunks/app/(marketing)/en/product/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/en/product/page-283946cf733426e8.js","/_next/static/chunks/app/(marketing)/en/register/hosting/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/en/register/hosting/page-3b2dd49c0e62bd73.js","/_next/static/chunks/app/(marketing)/en/register/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/en/register/page-7e23702d90d01ef3.js","/_next/static/chunks/app/(marketing)/en/solutions/[slug]/page-beff929ed29d1417.js","/_next/static/chunks/app/(marketing)/en/solutions/page-15815196478887cd.js","/_next/static/chunks/app/(marketing)/en/track/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/en/track/page-ed248941db5c912b.js","/_next/static/chunks/app/(marketing)/guides/[slug]/page-60f3f22382f1ce41.js","/_next/static/chunks/app/(marketing)/guides/page-b6a81186bda5a204.js","/_next/static/chunks/app/(marketing)/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/page-eb824294d08bc698.js","/_next/static/chunks/app/(marketing)/pricing/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/pricing/page-6598e7a23abf63a3.js","/_next/static/chunks/app/(marketing)/product/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/product/page-6a00e177cd332958.js","/_next/static/chunks/app/(marketing)/register/hosting/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/register/hosting/page-d75d3a0eea706d1d.js","/_next/static/chunks/app/(marketing)/register/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/register/page-280bf7a3eba97ca4.js","/_next/static/chunks/app/(marketing)/solutions/[slug]/page-25319ad66b0b54d0.js","/_next/static/chunks/app/(marketing)/solutions/page-4c387df3e6451ce0.js","/_next/static/chunks/app/(marketing)/track/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/track/page-05d361ba53962027.js","/_next/static/chunks/app/_not-found/page-93f5ecd9b5a1b8d5.js","/_next/static/chunks/app/activate-owner/layout-9111370ccccd4922.js","/_next/static/chunks/app/activate-owner/page-0c96893226839d69.js","/_next/static/chunks/app/forgot-password/layout-9111370ccccd4922.js","/_next/static/chunks/app/forgot-password/page-60b6947a59f3d422.js","/_next/static/chunks/app/layout-71f8a6757037cb13.js","/_next/static/chunks/app/login/layout-9111370ccccd4922.js","/_next/static/chunks/app/login/page-99f39b42534d18cc.js","/_next/static/chunks/app/reset-password/layout-9111370ccccd4922.js","/_next/static/chunks/app/reset-password/page-74a607793ac83ab1.js","/_next/static/chunks/app/robots.txt/route-9111370ccccd4922.js","/_next/static/chunks/app/sitemap.xml/route-9111370ccccd4922.js","/_next/static/chunks/framework-ac871cde7d705c3a.js","/_next/static/chunks/main-61969269e7b3dad5.js","/_next/static/chunks/main-app-d3c2614b980cfab3.js","/_next/static/chunks/pages/_app-c0e3f7ff6ef43cb0.js","/_next/static/chunks/pages/_error-6bf3d2bf6fe2d033.js","/_next/static/chunks/polyfills-42372ed130431b0a.js","/_next/static/chunks/webpack-91ffaed1d638f79f.js","/_next/static/css/81127cc7577d128a.css","/_next/static/media/011e180705008d6f-s.woff2","/_next/static/media/19cfc7226ec3afaa-s.woff2","/_next/static/media/1ebb550cd0a67fc6-s.p.woff2","/_next/static/media/21350d82a1f187e9-s.woff2","/_next/static/media/3dc379dc9b5dec12-s.p.woff2","/_next/static/media/58c726479f69cacd-s.woff2","/_next/static/media/58f386aa6b1a2a92-s.woff2","/_next/static/media/63a79a6cf340c5d2-s.p.woff2","/_next/static/media/7ba5fb2a8c88521c-s.woff2","/_next/static/media/8e9860b6e62d6359-s.woff2","/_next/static/media/92eeb95d069020cc-s.woff2","/_next/static/media/98e207f02528a563-s.p.woff2","/_next/static/media/99dcf268bda04fe5-s.woff2","/_next/static/media/ba9851c3c22cd980-s.woff2","/_next/static/media/bd9c8c62ffadd9dd-s.p.woff2","/_next/static/media/c5f10e9e72d35c52-s.woff2","/_next/static/media/c5fe6dc8356a8c31-s.woff2","/_next/static/media/cc8b755e9c1ba115-s.woff2","/_next/static/media/ce401babc0566bc1-s.woff2","/_next/static/media/d29838c109ef09b4-s.woff2","/_next/static/media/d3ebbfd689654d3a-s.p.woff2","/_next/static/media/dd994fbf464986f0-s.p.woff2","/_next/static/media/df0a9ae256c0569c-s.woff2","/_next/static/media/e40af3453d7c920a-s.woff2","/_next/static/media/e4af272ccee01ff0-s.p.woff2","/_next/static/media/e97026df054cf2a3-s.woff2","/_next/static/media/ef4d5661765d0e49-s.woff2","/_next/static/media/f15f45d13243c643-s.woff2","/_next/static/media/f952393b67d608ec-s.p.woff2","/icons/apple-touch-icon.png","/icons/badge-96.png","/icons/icon-192.png","/icons/icon-512.png","/icons/icon-maskable-192.png","/icons/icon-maskable-512.png","/manifest.webmanifest"];
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
