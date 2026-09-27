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
const BUILD = "ULewUH4rpKXf0gCzH3teW";
const CACHE = `vezano-shell-${BUILD}`;
// Every screen of the app, so the person lands on the page they asked for
// with no network — never on a different one. Filled in at build time from
// the export; the list below is the floor the PWA manifest relies on.
const PRECACHE_PAGES = ["/", "/login/", "/dashboard/", "/sales/", "/inventory/", "/returns/"];
const PRECACHE_APP_PAGES = ["/activate-owner/","/crm/","/customer-records/","/dashboard/","/debts/","/finance/","/forgot-password/","/hr/","/inventory/","/labels/","/login/","/logs/","/org/","/platform-activity/","/platform-analytics/","/platform-companies/","/platform-errors/","/platform-finance/","/platform-leads/","/platform-plans/","/platform-registrations/","/platform-seo/","/platform-subscriptions/","/platform-team/","/platform-team/member/","/platform/","/purchasing/","/reports/","/reset-password/","/returns/","/sales/","/settings/","/subscription/","/supplier-records/","/track/","/users/","/users/detail/","/web-orders/","/website/"];
// Every hashed chunk, stylesheet and font of this build, plus the manifest
// and icons — filled in at build time from the export.
const PRECACHE_ASSETS = ["/_next/static/ULewUH4rpKXf0gCzH3teW/_buildManifest.js","/_next/static/ULewUH4rpKXf0gCzH3teW/_ssgManifest.js","/_next/static/chunks/1328-f61aca8e87377237.js","/_next/static/chunks/1391-0b93ee9d9f7c21e5.js","/_next/static/chunks/2126-66d72952c3971eda.js","/_next/static/chunks/2395-2840df6565c7c063.js","/_next/static/chunks/2901-88da629a5face03f.js","/_next/static/chunks/2906-7e07ec2edf393ed5.js","/_next/static/chunks/2942-8fee8566988634b0.js","/_next/static/chunks/3415-ad947cbf8a27df6f.js","/_next/static/chunks/3431-86d1e29b5623eaf2.js","/_next/static/chunks/3995-193cf33b08e91925.js","/_next/static/chunks/40b91c18-03576e02c01e0947.js","/_next/static/chunks/4200-086e4dd05ced843c.js","/_next/static/chunks/4265-101243f1e4282e78.js","/_next/static/chunks/4353-82f00cb0b3d556b9.js","/_next/static/chunks/4473-8ea572ad178595e9.js","/_next/static/chunks/476-fc85ff3f4740c2ac.js","/_next/static/chunks/4838-c316258577a956ac.js","/_next/static/chunks/4863-3f2a95eec454e764.js","/_next/static/chunks/5405.a2853eec62072dae.js","/_next/static/chunks/5410-087bc64c21c04d17.js","/_next/static/chunks/6100-1fc6b211fc806fee.js","/_next/static/chunks/6579-047551cd8b13d2a8.js","/_next/static/chunks/6702-5a33da0ccd8afcac.js","/_next/static/chunks/689-8a8ebcacd8accd22.js","/_next/static/chunks/7536-15fbefc9cc695446.js","/_next/static/chunks/7769-313f6fad97c64c58.js","/_next/static/chunks/8117-220f357cdf1dced1.js","/_next/static/chunks/8430-f929184bb61c728a.js","/_next/static/chunks/8890-01971f9367d4d1b0.js","/_next/static/chunks/9265-7b58b312cc89db09.js","/_next/static/chunks/9394-b03e7326d8e6febd.js","/_next/static/chunks/9681-91b24db0c6ce4433.js","/_next/static/chunks/9865-d844f91f833a30d6.js","/_next/static/chunks/app/(app)/crm/page-e780a5fda791d5cd.js","/_next/static/chunks/app/(app)/customer-records/page-2f891c39420558d1.js","/_next/static/chunks/app/(app)/dashboard/page-814c40e806dede94.js","/_next/static/chunks/app/(app)/debts/page-20329935eb36d839.js","/_next/static/chunks/app/(app)/finance/page-72c813856bc16a4c.js","/_next/static/chunks/app/(app)/hr/page-cfae0b3ed5afb9c4.js","/_next/static/chunks/app/(app)/inventory/page-7642a2b600a0a521.js","/_next/static/chunks/app/(app)/labels/page-a57947c928890e2e.js","/_next/static/chunks/app/(app)/layout-7dd5e4992d249e97.js","/_next/static/chunks/app/(app)/logs/page-7d4dbbe89d66b461.js","/_next/static/chunks/app/(app)/org/page-f65497c62cd46b62.js","/_next/static/chunks/app/(app)/platform-activity/page-c8c111e2864bda73.js","/_next/static/chunks/app/(app)/platform-analytics/page-f30a3eb01b412847.js","/_next/static/chunks/app/(app)/platform-companies/page-e7eb8b28a3782e41.js","/_next/static/chunks/app/(app)/platform-errors/page-db50a461acc6972a.js","/_next/static/chunks/app/(app)/platform-finance/page-47249866a33f5419.js","/_next/static/chunks/app/(app)/platform-leads/page-2cd480a423948a06.js","/_next/static/chunks/app/(app)/platform-plans/page-0049fc33d94f1ad3.js","/_next/static/chunks/app/(app)/platform-registrations/page-df11a0d6b3258d7e.js","/_next/static/chunks/app/(app)/platform-seo/page-a6edddfe1f7d38a8.js","/_next/static/chunks/app/(app)/platform-subscriptions/page-77e50f689c0ee6ad.js","/_next/static/chunks/app/(app)/platform-team/member/page-05aa4f0042ff1837.js","/_next/static/chunks/app/(app)/platform-team/page-b10cdfd1e71b2cd8.js","/_next/static/chunks/app/(app)/platform/page-9b161589a2370c24.js","/_next/static/chunks/app/(app)/purchasing/page-c755a49e0e60feb4.js","/_next/static/chunks/app/(app)/reports/page-881ba17adc957ec2.js","/_next/static/chunks/app/(app)/returns/page-978795b14deba9e6.js","/_next/static/chunks/app/(app)/sales/page-5ca37efa9adffa61.js","/_next/static/chunks/app/(app)/settings/page-5cb4af149ff91c82.js","/_next/static/chunks/app/(app)/subscription/page-96e74b1a07f5a903.js","/_next/static/chunks/app/(app)/supplier-records/page-ab5e7aabe7aae2da.js","/_next/static/chunks/app/(app)/users/detail/page-46910fcd5d183dce.js","/_next/static/chunks/app/(app)/users/page-1ddf23ee96fe22a4.js","/_next/static/chunks/app/(app)/web-orders/page-5c794c557744ad6e.js","/_next/static/chunks/app/(app)/website/page-1f0232be29cd858d.js","/_next/static/chunks/app/(marketing)/compare/[slug]/page-40a6eb7f9f01294d.js","/_next/static/chunks/app/(marketing)/en/compare/[slug]/page-1485dfd72176ec60.js","/_next/static/chunks/app/(marketing)/en/guides/[slug]/page-282f15af9d80f8be.js","/_next/static/chunks/app/(marketing)/en/guides/page-035049b87e0cfd95.js","/_next/static/chunks/app/(marketing)/en/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/en/page-2091525f3cca6a77.js","/_next/static/chunks/app/(marketing)/en/pricing/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/en/pricing/page-45230248a1573237.js","/_next/static/chunks/app/(marketing)/en/product/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/en/product/page-87c8d58ffb5f51cc.js","/_next/static/chunks/app/(marketing)/en/register/hosting/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/en/register/hosting/page-3ed9e5db8764ab91.js","/_next/static/chunks/app/(marketing)/en/register/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/en/register/page-e4d7a3a91f2afdba.js","/_next/static/chunks/app/(marketing)/en/solutions/[slug]/page-8ae7d4e19acd45b0.js","/_next/static/chunks/app/(marketing)/en/solutions/page-6422483b8b337876.js","/_next/static/chunks/app/(marketing)/en/track/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/en/track/page-f4e5aefe8e00619c.js","/_next/static/chunks/app/(marketing)/guides/[slug]/page-4b938cc4c6f179f3.js","/_next/static/chunks/app/(marketing)/guides/page-d13099554457e154.js","/_next/static/chunks/app/(marketing)/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/page-897be945dda6b711.js","/_next/static/chunks/app/(marketing)/pricing/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/pricing/page-eafd4b5baaddfd98.js","/_next/static/chunks/app/(marketing)/product/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/product/page-fd4e6d593124d37c.js","/_next/static/chunks/app/(marketing)/register/hosting/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/register/hosting/page-f904ac5c6cf7b8b2.js","/_next/static/chunks/app/(marketing)/register/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/register/page-cb0f2ea65811f8af.js","/_next/static/chunks/app/(marketing)/solutions/[slug]/page-7d28a806748b7546.js","/_next/static/chunks/app/(marketing)/solutions/page-1e820ca33e1126a0.js","/_next/static/chunks/app/(marketing)/track/layout-9111370ccccd4922.js","/_next/static/chunks/app/(marketing)/track/page-e8e519f32ad103c1.js","/_next/static/chunks/app/_not-found/page-93f5ecd9b5a1b8d5.js","/_next/static/chunks/app/activate-owner/layout-9111370ccccd4922.js","/_next/static/chunks/app/activate-owner/page-24cb1dce68d0bbc7.js","/_next/static/chunks/app/forgot-password/layout-9111370ccccd4922.js","/_next/static/chunks/app/forgot-password/page-45fafc311b765f45.js","/_next/static/chunks/app/layout-62d68cad1b425e75.js","/_next/static/chunks/app/login/layout-9111370ccccd4922.js","/_next/static/chunks/app/login/page-ed87cc15cb8ccf63.js","/_next/static/chunks/app/reset-password/layout-9111370ccccd4922.js","/_next/static/chunks/app/reset-password/page-f9f0579651fd22c7.js","/_next/static/chunks/app/robots.txt/route-9111370ccccd4922.js","/_next/static/chunks/app/sitemap.xml/route-9111370ccccd4922.js","/_next/static/chunks/framework-ac871cde7d705c3a.js","/_next/static/chunks/main-61969269e7b3dad5.js","/_next/static/chunks/main-app-d3c2614b980cfab3.js","/_next/static/chunks/pages/_app-c0e3f7ff6ef43cb0.js","/_next/static/chunks/pages/_error-6bf3d2bf6fe2d033.js","/_next/static/chunks/polyfills-42372ed130431b0a.js","/_next/static/chunks/webpack-91ffaed1d638f79f.js","/_next/static/css/81127cc7577d128a.css","/_next/static/media/011e180705008d6f-s.woff2","/_next/static/media/19cfc7226ec3afaa-s.woff2","/_next/static/media/1ebb550cd0a67fc6-s.p.woff2","/_next/static/media/21350d82a1f187e9-s.woff2","/_next/static/media/3dc379dc9b5dec12-s.p.woff2","/_next/static/media/58c726479f69cacd-s.woff2","/_next/static/media/58f386aa6b1a2a92-s.woff2","/_next/static/media/63a79a6cf340c5d2-s.p.woff2","/_next/static/media/7ba5fb2a8c88521c-s.woff2","/_next/static/media/8e9860b6e62d6359-s.woff2","/_next/static/media/92eeb95d069020cc-s.woff2","/_next/static/media/98e207f02528a563-s.p.woff2","/_next/static/media/99dcf268bda04fe5-s.woff2","/_next/static/media/ba9851c3c22cd980-s.woff2","/_next/static/media/bd9c8c62ffadd9dd-s.p.woff2","/_next/static/media/c5f10e9e72d35c52-s.woff2","/_next/static/media/c5fe6dc8356a8c31-s.woff2","/_next/static/media/cc8b755e9c1ba115-s.woff2","/_next/static/media/ce401babc0566bc1-s.woff2","/_next/static/media/d29838c109ef09b4-s.woff2","/_next/static/media/d3ebbfd689654d3a-s.p.woff2","/_next/static/media/dd994fbf464986f0-s.p.woff2","/_next/static/media/df0a9ae256c0569c-s.woff2","/_next/static/media/e40af3453d7c920a-s.woff2","/_next/static/media/e4af272ccee01ff0-s.p.woff2","/_next/static/media/e97026df054cf2a3-s.woff2","/_next/static/media/ef4d5661765d0e49-s.woff2","/_next/static/media/f15f45d13243c643-s.woff2","/_next/static/media/f952393b67d608ec-s.p.woff2","/icons/apple-touch-icon.png","/icons/badge-96.png","/icons/icon-192.png","/icons/icon-512.png","/icons/icon-maskable-192.png","/icons/icon-maskable-512.png","/manifest.webmanifest"];
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
