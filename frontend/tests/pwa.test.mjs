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
  const precache = JSON.parse(sw.match(/const PRECACHE = (\[[^\]]*\])/)[1]);
  assert.ok(precache.includes(manifest.start_url), "start_url must open offline");
  for (const s of manifest.shortcuts) assert.ok(precache.includes(s.url), `${s.url} not precached`);
});

test("install state helpers are safe without a browser", async () => {
  const mod = await import("../lib/installPrompt.js");
  assert.equal(mod.isStandaloneDisplay(), false);
  assert.equal(await mod.isStoragePersisted(), false);
});
