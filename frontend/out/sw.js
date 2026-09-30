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
const BUILD = "v3BL2n8FSYBOAS_LvONbi";
const CACHE = `vezano-shell-${BUILD}`;
// Every screen of the app, so the person lands on the page they asked for
// with no network — never on a different one. Filled in at build time from
// the export; the list below is the floor the PWA manifest relies on.
const PRECACHE_PAGES = ["/", "/login/", "/dashboard/", "/sales/", "/inventory/", "/returns/"];
const PRECACHE_APP_PAGES = ["/activate-owner/","/crm/","/customer-records/","/dashboard/","/debts/","/finance/","/forgot-password/","/hr/","/inventory/","/labels/","/login/","/logs/","/org/","/platform-activity/","/platform-analytics/","/platform-companies/","/platform-errors/","/platform-finance/","/platform-leads/","/platform-plans/","/platform-registrations/","/platform-seo/","/platform-subscriptions/","/platform-team/","/platform-team/member/","/platform/","/purchasing/","/reports/","/reset-password/","/returns/","/sales/","/settings/","/subscription/","/supplier-records/","/track/","/users/","/users/detail/","/web-orders/","/website/"];
// Every hashed chunk, stylesheet and font of this build, plus the manifest
// and icons — filled in at build time from the export.
const PRECACHE_ASSETS = ["/_next/static/chunks/1054-91168850c8a0e13f.js","/_next/static/chunks/1077-bc668ed303b84d4e.js","/_next/static/chunks/196-1c5f1a59350663af.js","/_next/static/chunks/2017-7c70b4e3f4cf2c0e.js","/_next/static/chunks/2239-27e68465d2be41d7.js","/_next/static/chunks/2285-aead3ef713fd9a8f.js","/_next/static/chunks/2480-4c577b674e23797e.js","/_next/static/chunks/2549-095286aa79aa569c.js","/_next/static/chunks/2780-786059644088bb23.js","/_next/static/chunks/2841.7793a3cbaad1a1de.js","/_next/static/chunks/2951-11b7543808849921.js","/_next/static/chunks/3195-dd260d3f08d68dd5.js","/_next/static/chunks/4352-260b92b6ae205a56.js","/_next/static/chunks/4865.de705fe9bff98e58.js","/_next/static/chunks/5258-304c352661be95e1.js","/_next/static/chunks/5291-737dd779bc888305.js","/_next/static/chunks/5308-cab963b28151265f.js","/_next/static/chunks/5563-7171657d8c3a836e.js","/_next/static/chunks/5635-f9a3bb6b1946c5f2.js","/_next/static/chunks/5734-e3ff13cf03dd96c6.js","/_next/static/chunks/5840-2f31e777f867d861.js","/_next/static/chunks/5892-1c5570f5eec0400c.js","/_next/static/chunks/5945-be8df81b5d0bf58c.js","/_next/static/chunks/5959-2a566bc00a7f1db5.js","/_next/static/chunks/6713-23470aac1d119a56.js","/_next/static/chunks/6718-fbd1b85b22fd2607.js","/_next/static/chunks/6767.734bbcfe154a6c7c.js","/_next/static/chunks/7566-5fae5d85a95b5737.js","/_next/static/chunks/7928-c45bb1cd5e55ccd8.js","/_next/static/chunks/8366-7f2f1c8f26f16ace.js","/_next/static/chunks/8377-1e653f3e8da4a7f9.js","/_next/static/chunks/8382-981ba26e7f8bc528.js","/_next/static/chunks/870-45b955eb86a82351.js","/_next/static/chunks/8773-048b6dcd9c9a7aa8.js","/_next/static/chunks/8925-3534990babbb2d30.js","/_next/static/chunks/9301-eaef6b0d96d4d53d.js","/_next/static/chunks/9649-72974bb389a63ec0.js","/_next/static/chunks/9827-50bed4f900cc25f6.js","/_next/static/chunks/9899-18dcf26cdd2226c6.js","/_next/static/chunks/9931-60f36fca9f9f9344.js","/_next/static/chunks/app/(app)/crm/page-f7ade993f08ac5cd.js","/_next/static/chunks/app/(app)/customer-records/page-868889641a89e203.js","/_next/static/chunks/app/(app)/dashboard/page-78282f03892dd24f.js","/_next/static/chunks/app/(app)/debts/page-f7ec2dd6f0618d59.js","/_next/static/chunks/app/(app)/finance/page-5706277d672395b6.js","/_next/static/chunks/app/(app)/hr/page-e95661c5d881edf1.js","/_next/static/chunks/app/(app)/inventory/page-45bc6f990e78cd94.js","/_next/static/chunks/app/(app)/labels/page-a4c1014d45cec423.js","/_next/static/chunks/app/(app)/layout-cea3ffa48f44c0e3.js","/_next/static/chunks/app/(app)/logs/page-bbd2d7fc5a6f835f.js","/_next/static/chunks/app/(app)/org/page-0c0e46e398dfe2bb.js","/_next/static/chunks/app/(app)/platform-activity/page-7b0f33cb1a9a04fd.js","/_next/static/chunks/app/(app)/platform-analytics/page-20f64c4dcb0da305.js","/_next/static/chunks/app/(app)/platform-companies/page-db122f345446b72b.js","/_next/static/chunks/app/(app)/platform-errors/page-09f012ad4d800743.js","/_next/static/chunks/app/(app)/platform-finance/page-9f3956a6126bacfb.js","/_next/static/chunks/app/(app)/platform-leads/page-c9d59e3e4bc964e9.js","/_next/static/chunks/app/(app)/platform-plans/page-f64a700142e9679c.js","/_next/static/chunks/app/(app)/platform-registrations/page-59c699ef0af24f7b.js","/_next/static/chunks/app/(app)/platform-seo/page-ca5ca365badb906a.js","/_next/static/chunks/app/(app)/platform-subscriptions/page-7f95628578a5eedf.js","/_next/static/chunks/app/(app)/platform-team/member/page-5fc5c0369537a867.js","/_next/static/chunks/app/(app)/platform-team/page-2176e855be0dba36.js","/_next/static/chunks/app/(app)/platform/page-b6c78516f7bb8252.js","/_next/static/chunks/app/(app)/purchasing/page-0167587fea9917b1.js","/_next/static/chunks/app/(app)/reports/page-f859f6ee6730aab5.js","/_next/static/chunks/app/(app)/returns/page-0ed8dffb8bbd5ecb.js","/_next/static/chunks/app/(app)/sales/page-da7790d9edc2ff4a.js","/_next/static/chunks/app/(app)/settings/page-5a7ce4e4ff4bcd36.js","/_next/static/chunks/app/(app)/subscription/page-60817a3402ee0fa8.js","/_next/static/chunks/app/(app)/supplier-records/page-e366fa0d6f79e012.js","/_next/static/chunks/app/(app)/users/detail/page-35ef9f604b81bbd0.js","/_next/static/chunks/app/(app)/users/page-63aa096f0236dee5.js","/_next/static/chunks/app/(app)/web-orders/page-51a3d17ee15a454b.js","/_next/static/chunks/app/(app)/website/page-6ec7c423b922f6ad.js","/_next/static/chunks/app/(marketing)/compare/[slug]/page-13ed05d25a20c5b3.js","/_next/static/chunks/app/(marketing)/en/compare/[slug]/page-57201dd87e30805a.js","/_next/static/chunks/app/(marketing)/en/guides/[slug]/page-8373859a19e17f9c.js","/_next/static/chunks/app/(marketing)/en/guides/page-d5405b41ed8b9e5c.js","/_next/static/chunks/app/(marketing)/en/layout-43d8c731b299024d.js","/_next/static/chunks/app/(marketing)/en/page-8c3483f61eecda49.js","/_next/static/chunks/app/(marketing)/en/pricing/layout-43d8c731b299024d.js","/_next/static/chunks/app/(marketing)/en/pricing/page-8547bb76f638f377.js","/_next/static/chunks/app/(marketing)/en/product/layout-43d8c731b299024d.js","/_next/static/chunks/app/(marketing)/en/product/page-3262411b47abe43c.js","/_next/static/chunks/app/(marketing)/en/register/hosting/layout-43d8c731b299024d.js","/_next/static/chunks/app/(marketing)/en/register/hosting/page-e6eb0c5e7a12725a.js","/_next/static/chunks/app/(marketing)/en/register/layout-43d8c731b299024d.js","/_next/static/chunks/app/(marketing)/en/register/page-4199851d0c9966e3.js","/_next/static/chunks/app/(marketing)/en/solutions/[slug]/page-186b2e439c705a92.js","/_next/static/chunks/app/(marketing)/en/solutions/page-ac95f73a8a233e15.js","/_next/static/chunks/app/(marketing)/en/track/layout-43d8c731b299024d.js","/_next/static/chunks/app/(marketing)/en/track/page-8342b884abee6798.js","/_next/static/chunks/app/(marketing)/guides/[slug]/page-5eeabe76dcd29644.js","/_next/static/chunks/app/(marketing)/guides/page-7f1a1aa4839b7fa7.js","/_next/static/chunks/app/(marketing)/layout-6eb3110fa4694d24.js","/_next/static/chunks/app/(marketing)/page-779661481862960a.js","/_next/static/chunks/app/(marketing)/pricing/layout-43d8c731b299024d.js","/_next/static/chunks/app/(marketing)/pricing/page-95d0da9665b39057.js","/_next/static/chunks/app/(marketing)/product/layout-43d8c731b299024d.js","/_next/static/chunks/app/(marketing)/product/page-37c961b5b5838ff4.js","/_next/static/chunks/app/(marketing)/register/hosting/layout-43d8c731b299024d.js","/_next/static/chunks/app/(marketing)/register/hosting/page-cfa220e24c74c69f.js","/_next/static/chunks/app/(marketing)/register/layout-43d8c731b299024d.js","/_next/static/chunks/app/(marketing)/register/page-1cb4e49c8713f4d4.js","/_next/static/chunks/app/(marketing)/solutions/[slug]/page-8cd30885be48f931.js","/_next/static/chunks/app/(marketing)/solutions/page-17b98689474a2cc6.js","/_next/static/chunks/app/(marketing)/track/layout-43d8c731b299024d.js","/_next/static/chunks/app/(marketing)/track/page-5f88ce033fe73120.js","/_next/static/chunks/app/_not-found/page-68a0584aa6a8d18f.js","/_next/static/chunks/app/activate-owner/layout-84dd843358efab0b.js","/_next/static/chunks/app/activate-owner/page-ccdd84b4659d943f.js","/_next/static/chunks/app/forgot-password/layout-84dd843358efab0b.js","/_next/static/chunks/app/forgot-password/page-3b471a1e29c523e9.js","/_next/static/chunks/app/layout-48c8789ab8bee7d5.js","/_next/static/chunks/app/login/layout-84dd843358efab0b.js","/_next/static/chunks/app/login/page-3f2aa058824eb266.js","/_next/static/chunks/app/reset-password/layout-84dd843358efab0b.js","/_next/static/chunks/app/reset-password/page-6d58dcf0b35234ab.js","/_next/static/chunks/app/robots.txt/route-43d8c731b299024d.js","/_next/static/chunks/app/sitemap.xml/route-43d8c731b299024d.js","/_next/static/chunks/e46ef968-b68f361a13319b06.js","/_next/static/chunks/framework-e856097ae3f00b5b.js","/_next/static/chunks/main-161e8115e5182cdb.js","/_next/static/chunks/main-app-3877a70d26e4c09e.js","/_next/static/chunks/pages/_app-d0a68f56507e1d03.js","/_next/static/chunks/pages/_error-87b7d7c4dcd46628.js","/_next/static/chunks/polyfills-42372ed130431b0a.js","/_next/static/chunks/webpack-190cbb524a575962.js","/_next/static/css/3a004b2118e1801b.css","/_next/static/media/011e180705008d6f.woff2","/_next/static/media/19cfc7226ec3afaa.woff2","/_next/static/media/1ebb550cd0a67fc6.p.woff2","/_next/static/media/21350d82a1f187e9.woff2","/_next/static/media/3dc379dc9b5dec12.p.woff2","/_next/static/media/58c726479f69cacd.woff2","/_next/static/media/58f386aa6b1a2a92.woff2","/_next/static/media/63a79a6cf340c5d2.p.woff2","/_next/static/media/7ba5fb2a8c88521c.woff2","/_next/static/media/8e9860b6e62d6359.woff2","/_next/static/media/92eeb95d069020cc.woff2","/_next/static/media/98e207f02528a563.p.woff2","/_next/static/media/99dcf268bda04fe5.woff2","/_next/static/media/ba9851c3c22cd980.woff2","/_next/static/media/bd9c8c62ffadd9dd.p.woff2","/_next/static/media/c5f10e9e72d35c52.woff2","/_next/static/media/c5fe6dc8356a8c31.woff2","/_next/static/media/cc8b755e9c1ba115.woff2","/_next/static/media/ce401babc0566bc1.woff2","/_next/static/media/d29838c109ef09b4.woff2","/_next/static/media/d3ebbfd689654d3a.p.woff2","/_next/static/media/dd994fbf464986f0.p.woff2","/_next/static/media/df0a9ae256c0569c.woff2","/_next/static/media/e40af3453d7c920a.woff2","/_next/static/media/e4af272ccee01ff0.p.woff2","/_next/static/media/e97026df054cf2a3.woff2","/_next/static/media/ef4d5661765d0e49.woff2","/_next/static/media/f15f45d13243c643.woff2","/_next/static/media/f952393b67d608ec.p.woff2","/_next/static/v3BL2n8FSYBOAS_LvONbi/_buildManifest.js","/_next/static/v3BL2n8FSYBOAS_LvONbi/_ssgManifest.js","/icons/apple-touch-icon.png","/icons/badge-96.png","/icons/icon-192.png","/icons/icon-512.png","/icons/icon-maskable-192.png","/icons/icon-maskable-512.png","/manifest.webmanifest"];
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
