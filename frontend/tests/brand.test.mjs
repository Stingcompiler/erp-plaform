import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { BRAND_TEAL, markElements, markSvg, tierFor } from "../lib/brandMark.js";
import { LEGACY_NAMES, SITE_NAME, SITE_NAME_LATIN } from "../lib/site.js";

const read = (p) => readFileSync(fileURLToPath(new URL(`../${p}`, import.meta.url)), "utf8");

// The product is «فيزانو برو» / "Vezano Pro" (owner decision, 2026-09).
test("the site name is the new brand in both languages", () => {
  assert.equal(SITE_NAME, "فيزانو برو");
  assert.equal(SITE_NAME_LATIN, "Vezano Pro");
  assert.deepEqual(LEGACY_NAMES, ["Vezano", "فيزانو"]);
});

test("the homepage title and the site title template carry the new name", () => {
  const meta = read("lib/marketingMeta.js");
  assert.match(meta, /"\/": \{\s*title: `\$\{SITE_NAME\} \|/);
  assert.match(meta, /"\/": \{\s*title: `\$\{SITE_NAME_LATIN\} \|/);
  const layout = read("app/layout.js");
  assert.match(layout, /default: `\$\{SITE_NAME\} \|/);
  assert.match(layout, /template: `%s \| \$\{SITE_NAME\}`/);
});

test("the PWA manifest is named «فيزانو برو»", () => {
  const manifest = JSON.parse(read("public/manifest.webmanifest"));
  assert.equal(manifest.name, "فيزانو برو");
  assert.equal(manifest.short_name, "فيزانو برو");
  assert.ok(manifest.short_name.length <= 12, "short_name must fit under a home-screen icon");
});

test("no visible copy still says the bare old name", () => {
  for (const file of ["lib/i18n.js", "lib/marketingI18n.js", "lib/marketingMeta.js"]) {
    const lines = read(file).split("\n").filter((line) => !/^\s*(\/\/|\/\*|\*)/.test(line));
    for (const line of lines) {
      assert.ok(!/فيزانو(?! برو)/.test(line), `${file}: ${line.trim()}`);
      assert.ok(!/\bVezano\b(?! Pro)/.test(line), `${file}: ${line.trim()}`);
    }
  }
});

test("the logo mark picks its tier by rendered size", () => {
  assert.equal(tierFor(512), "full");
  assert.equal(tierFor(48), "full");
  assert.equal(tierFor(47), "medium");
  assert.equal(tierFor(24), "medium");
  assert.equal(tierFor(23), "small");
  // Full has the sync arc and its arrowhead beyond the branches; medium
  // drops them; small is the branches and one hub square.
  const paths = (tier) => markElements(tier).filter((e) => e.tag === "path").length;
  assert.equal(paths("full"), 3);
  assert.equal(paths("medium"), 1);
  assert.deepEqual(markElements("small").map((e) => e.tag), ["path", "rect"]);
  assert.ok(!markSvg({ mono: true }).includes(BRAND_TEAL), "mono has no teal tile");
});

test("the app icons are generated from the design/brand masters", () => {
  assert.equal(read("public/icons/icon.svg"), read("../design/brand/mark-full.svg"));
  assert.equal(read("public/icons/favicon.svg"), read("../design/brand/mark-small.svg"));
  assert.equal(read("public/icons/icon-maskable.svg"), read("../design/brand/mark-maskable.svg"));
});

test("favicon.ico carries 16 and 32 px icons, and the notification badge exists", () => {
  const ico = readFileSync(fileURLToPath(new URL("../public/favicon.ico", import.meta.url)));
  assert.equal(ico.readUInt16LE(2), 1);
  assert.equal(ico.readUInt16LE(4), 2);
  assert.deepEqual([ico[6], ico[22]], [16, 32]);
  const badge = /badge: "([^"]+)"/.exec(read("public/sw.js"))[1];
  assert.ok(read(`public${badge}`).length > 0);
});
