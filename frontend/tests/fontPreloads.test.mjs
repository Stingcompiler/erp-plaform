import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { KEEP, keepFor, preloadFaces, prune } from "../scripts/font-preloads.mjs";

const CSS = [
  "@font-face{font-family:Inter;unicode-range:u+00??,u+0131;src:url(/_next/static/media/inter.p.woff2) format(\"woff2\")}",
  "@font-face{font-family:Inter;unicode-range:u+0100-02ba;src:url(/_next/static/media/inter-ext.woff2) format(\"woff2\")}",
  "@font-face{font-family:Sora;src:url(/_next/static/media/sora.p.woff2) format(\"woff2\");font-weight:700;unicode-range:U+0000-00FF}",
  "@font-face{font-family:IBM Plex Mono;src:url(/_next/static/media/mono.p.woff2) format(\"woff2\");unicode-range:U+0000-00FF}",
  "@font-face{font-family:Tajawal;unicode-range:u+06??,u+0750-077f;src:url(/_next/static/media/taj.p.woff2) format(\"woff2\")}",
  "@font-face{font-family:Tajawal;src:url(/_next/static/media/taj-latin.woff2) format(\"woff2\");unicode-range:U+0000-00FF}",
  "@font-face{font-family:Readex Pro;src:url(/_next/static/media/rx-ar.p.woff2) format(\"woff2\");unicode-range:U+0600-06FF}",
  "@font-face{font-family:Readex Pro;src:url(/_next/static/media/rx-la.p.woff2) format(\"woff2\");unicode-range:U+0000-00FF}",
].join("");

const link = (name) => `<link rel="preload" href="/_next/static/media/${name}.p.woff2" as="font" crossorigin="" type="font/woff2"/>`;
const hint = (name) => `:HL[\\"/_next/static/media/${name}.p.woff2\\",\\"font\\",{\\"crossOrigin\\":\\"\\",\\"type\\":\\"font/woff2\\"}]\\n`;
const row = (name) => `:HL["/_next/static/media/${name}.p.woff2","font",{"crossOrigin":"","type":"font/woff2"}]\n`;
const ALL = ["inter", "sora", "mono", "taj", "rx-ar", "rx-la"];

test("each language keeps its own text faces, no wordmark and no mono", () => {
  const faces = preloadFaces(CSS);
  assert.equal(faces.size, 6, "only .p.woff2 faces are preloadable");
  assert.deepEqual([...keepFor("ar", faces)].sort(), ["/_next/static/media/taj.p.woff2"]);
  assert.deepEqual([...keepFor("en", faces)].sort(), ["/_next/static/media/inter.p.woff2", "/_next/static/media/sora.p.woff2"]);
  assert.ok(!KEEP.ar.concat(KEEP.en).some(([family]) => /mono|readex/i.test(family)));
});

test("links, inline hints and index.txt rows are pruned alike", () => {
  const keep = keepFor("en", preloadFaces(CSS));
  const html = `<head>${ALL.map(link).join("")}</head><script>self.__next_f.push([1,"${ALL.map(hint).join("")}0:{}"])</script>`;
  const pruned = prune(html, keep, "html");
  for (const name of ["inter", "sora"]) assert.ok(pruned.includes(`${name}.p.woff2" as="font"`) && pruned.includes(`media/${name}.p.woff2\\",\\"font`), name);
  for (const name of ["mono", "taj", "rx-ar", "rx-la"]) assert.ok(!pruned.includes(`${name}.p.woff2`), name);
  assert.ok(pruned.endsWith(`0:{}"])</script>`));
  const txt = `1:"$Sreact.fragment"\n${ALL.map(row).join("")}0:{}\n`;
  const prunedTxt = prune(txt, keep, "txt");
  assert.equal(prunedTxt, `1:"$Sreact.fragment"\n${["inter", "sora"].map(row).join("")}0:{}\n`);
});

test("the build runs it before the service worker is stamped", () => {
  const pkg = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));
  assert.match(pkg.scripts.build, /next build && node scripts\/font-preloads\.mjs && node scripts\/stamp-sw\.mjs/);
});
