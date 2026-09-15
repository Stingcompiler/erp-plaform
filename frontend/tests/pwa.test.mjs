import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

const pub = (p) => fileURLToPath(new URL(`../public/${p}`, import.meta.url));
const manifest = JSON.parse(readFileSync(pub("manifest.webmanifest"), "utf8"));

// Chromium's installability bar: a name, a start_url inside scope, a
// standalone display, and 192 + 512 PNG icons that actually exist.
test("manifest satisfies the installability criteria", () => {
  assert.ok(manifest.name && manifest.short_name);
  assert.equal(manifest.display, "standalone");
  assert.ok(manifest.start_url.startsWith(manifest.scope));
  const sizes = manifest.icons.filter((i) => i.purpose === "any").map((i) => i.sizes);
  assert.ok(sizes.includes("192x192") && sizes.includes("512x512"));
  assert.ok(manifest.icons.some((i) => i.purpose === "maskable"));
  for (const icon of manifest.icons) {
    assert.ok(existsSync(pub(icon.src.replace(/^\//, ""))), `${icon.src} missing`);
    const png = readFileSync(pub(icon.src.replace(/^\//, "")));
    assert.equal(png.toString("hex", 0, 8), "89504e470d0a1a0a", `${icon.src} is not a PNG`);
    const [w, h] = [png.readUInt32BE(16), png.readUInt32BE(20)];
    assert.equal(`${w}x${h}`, icon.sizes, `${icon.src} declared ${icon.sizes}, is ${w}x${h}`);
  }
});

test("shortcuts and start page are routes the service worker precaches", () => {
  const sw = readFileSync(pub("sw.js"), "utf8");
  const precache = JSON.parse(sw.match(/const PRECACHE_PAGES = (\[[^\]]*\])/)[1]);
  assert.ok(precache.includes(manifest.start_url), "start_url must open offline");
  for (const s of manifest.shortcuts) assert.ok(precache.includes(s.url), `${s.url} not precached`);
});

test("install state helpers are safe without a browser", async () => {
  const mod = await import("../lib/installPrompt.js");
  assert.equal(mod.isStandaloneDisplay(), false);
  assert.equal(await mod.isStoragePersisted(), false);
});

test("service worker never activates a new build on its own", () => {
  const sw = readFileSync(pub("sw.js"), "utf8");
  const installer = sw.slice(sw.indexOf('addEventListener("install"'), sw.indexOf('addEventListener("activate"'));
  assert.ok(!installer.includes("skipWaiting"), "install must not skipWaiting");
  assert.ok(sw.includes('event.data?.type === "SKIP_WAITING"'), "page-driven takeover missing");
  assert.ok(sw.includes("cache.addAll("), "install must be atomic (addAll)");
  assert.ok(sw.includes("__PRECACHE_ASSETS__"), "asset list placeholder missing");
});

test("stamp script lists every chunk, stylesheet, font, icon and the manifest", async () => {
  const { mkdtempSync, mkdirSync, writeFileSync } = await import("node:fs");
  const { tmpdir } = await import("node:os");
  const { join } = await import("node:path");
  const root = mkdtempSync(join(tmpdir(), "vezano-out-"));
  for (const f of ["_next/static/chunks/a.js", "_next/static/chunks/app/(app)/sales/page-1.js",
    "_next/static/css/x.css", "_next/static/media/f.woff2", "_next/static/chunks/a.js.map",
    "icons/icon-192.png", "manifest.webmanifest", "sales/index.html", "sales/index.txt"]) {
    mkdirSync(join(root, f, ".."), { recursive: true });
    writeFileSync(join(root, f), "x");
  }
  const { listPrecacheAssets } = await import("../scripts/stamp-sw.mjs");
  const assets = listPrecacheAssets(root);
  assert.deepEqual(assets, [
    "/_next/static/chunks/a.js", "/_next/static/chunks/app/(app)/sales/page-1.js",
    "/_next/static/css/x.css", "/_next/static/media/f.woff2",
    "/icons/icon-192.png", "/manifest.webmanifest",
  ]);
});
