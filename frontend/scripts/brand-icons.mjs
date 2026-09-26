// Brand assets from the one logo geometry in lib/brandMark.js.
//
//   node scripts/brand-icons.mjs            (from frontend/)
//     1. writes the master SVGs to design/brand/ (full, medium, small,
//        maskable, monochrome, and the light/dark lockups with the wordmark);
//     2. rasterises the app icons in public/ from those masters, and PNG
//        exports of each master to design/brand/png/.
//   node scripts/brand-icons.mjs --lockups
//     also renders the lockup PNGs, with Playwright's Chromium (the wordmark
//     is live Readex Pro text, loaded from Google Fonts, so it needs a
//     browser and a network connection).
//
// Uses sharp, which ships with Next.js in node_modules. Commit design/brand,
// public/icons and public/favicon.ico afterwards.
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import sharp from "sharp";

import { BRAND_TEAL, markSvg } from "../lib/brandMark.js";

const at = (base) => (p) => fileURLToPath(new URL(`${base}${p}`, import.meta.url));
const pub = at("../public/");
const design = at("../../design/brand/");
mkdirSync(design("png"), { recursive: true });

// The maskable safe zone is the central circle of radius 40%; at 0.8 the
// mark's farthest point (a branch node's rim) sits inside it.
const MASKABLE_INSET = 0.8;
const APPLE_INSET = 0.9;

// ---- 1. Masters -----------------------------------------------------------
const WORDMARK = {
  ar: { base: "فيزانو", pro: "برو", width: 330 },
  en: { base: "Vezano", pro: "Pro", width: 350 },
};
const THEMES = {
  light: { ink: "#12253b", pro: BRAND_TEAL },
  dark: { ink: "#f5f7fa", pro: "#37b0b8" },
};

// The mark (64×64) and the wordmark (Readex Pro 700, «برو»/"Pro" 500 in
// the accent) on one line, mark first in reading order: on the right for
// Arabic, on the left for English. Transparent background; the dark lockup
// is for dark surfaces.
function lockup(language, theme) {
  const { base, pro, width } = WORDMARK[language];
  const { ink, pro: accent } = THEMES[theme];
  const mark = markSvg({ size: 64 }).replace("<svg ", `<svg x="${language === "ar" ? width - 64 : 0}" y="8" `);
  const text = language === "ar"
    ? `<text x="${width - 84}" y="55" direction="rtl" text-anchor="start">${base} <tspan class="pro">${pro}</tspan></text>`
    : `<text x="84" y="55">${base} <tspan class="pro">${pro}</tspan></text>`;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} 80" width="${width}" height="80">
<!-- Wordmark: live text in Readex Pro 700 ("${pro}" 500). Install the font or open in a browser. -->
<style>@import url('https://fonts.googleapis.com/css2?family=Readex+Pro:wght@500;700&amp;display=swap');
text{font-family:'Readex Pro',sans-serif;font-weight:700;font-size:40px;fill:${ink}}.pro{font-weight:500;fill:${accent}}</style>
${mark}
${text}
</svg>
`;
}

const masters = {
  "mark-full.svg": markSvg({ tier: "full", size: 512, title: "Vezano Pro" }),
  "mark-medium.svg": markSvg({ tier: "medium", size: 64, title: "Vezano Pro" }),
  "mark-small.svg": markSvg({ tier: "small", size: 32, title: "Vezano Pro" }),
  "mark-maskable.svg": markSvg({ tier: "full", size: 512, shape: "square", inset: MASKABLE_INSET, title: "Vezano Pro" }),
  "mark-apple.svg": markSvg({ tier: "full", size: 180, shape: "square", inset: APPLE_INSET, title: "Vezano Pro" }),
  "mark-mono.svg": markSvg({ tier: "medium", size: 64, mono: true, title: "Vezano Pro" }),
  "lockup-ar-light.svg": lockup("ar", "light"),
  "lockup-ar-dark.svg": lockup("ar", "dark"),
  "lockup-en-light.svg": lockup("en", "light"),
  "lockup-en-dark.svg": lockup("en", "dark"),
};
for (const [name, svg] of Object.entries(masters)) writeFileSync(design(name), svg.endsWith("\n") ? svg : svg + "\n");

// ---- 2. Rasters from the masters ------------------------------------------
const master = (name) => readFileSync(design(name));

async function png(svg, size, { opaque = false, background } = {}) {
  // Rasterise at 4× the target, then downscale, for clean edges.
  const declared = Number(/width="(\d+)"/.exec(svg.toString())[1]);
  let image = sharp(svg, { density: (72 * 4 * size) / declared }).resize(size, size);
  if (opaque) image = image.flatten({ background: BRAND_TEAL }).removeAlpha();
  if (background) image = image.flatten({ background });
  return image.png({ compressionLevel: 9 }).toBuffer();
}

const outputs = [
  // The app (public/): what the manifest, the metadata and the service worker reference.
  [pub("icons/icon-192.png"), "mark-full.svg", 192],
  [pub("icons/icon-512.png"), "mark-full.svg", 512],
  [pub("icons/icon-maskable-192.png"), "mark-maskable.svg", 192],
  [pub("icons/icon-maskable-512.png"), "mark-maskable.svg", 512],
  [pub("icons/apple-touch-icon.png"), "mark-apple.svg", 180, { opaque: true }],
  // Exports for the record (design/brand/png/).
  [design("png/mark-full-512.png"), "mark-full.svg", 512],
  [design("png/mark-full-192.png"), "mark-full.svg", 192],
  [design("png/mark-full-48.png"), "mark-full.svg", 48],
  [design("png/mark-medium-32.png"), "mark-medium.svg", 32],
  [design("png/mark-medium-24.png"), "mark-medium.svg", 24],
  [design("png/mark-small-32.png"), "mark-small.svg", 32],
  [design("png/mark-small-16.png"), "mark-small.svg", 16],
  [design("png/mark-maskable-512.png"), "mark-maskable.svg", 512],
  [design("png/mark-apple-180.png"), "mark-apple.svg", 180, { opaque: true }],
  [design("png/mark-mono-512.png"), "mark-mono.svg", 512, { background: "#ffffff" }],
];
for (const [path, name, size, options] of outputs) writeFileSync(path, await png(master(name), size, options));

// SVG copies the app serves directly.
writeFileSync(pub("icons/icon.svg"), master("mark-full.svg"));
writeFileSync(pub("icons/icon-maskable.svg"), master("mark-maskable.svg"));
writeFileSync(pub("icons/favicon.svg"), master("mark-small.svg"));
writeFileSync(pub("icons/mark-mono.svg"), master("mark-mono.svg"));

// The Django public pages' platform mark (the store directory header): the
// medium tier at 36px, next to the wordmark, so hidden from screen readers.
writeFileSync(
  fileURLToPath(new URL("../../backend/website/templates/website/_logo_mark.html", import.meta.url)),
  "{# Generated by frontend/scripts/brand-icons.mjs from lib/brandMark.js; do not edit. #}\n" +
    markSvg({ tier: "medium", size: 36 }).replace("<svg ", '<svg class="vz-mark" aria-hidden="true" focusable="false" ') + "\n",
);

// Notification badge: Android draws only its alpha, so a transparent
// monochrome mark (medium tier) rather than the tile.
writeFileSync(pub("icons/badge-96.png"), await png(master("mark-mono.svg"), 96));

// favicon.ico: an ICO directory of PNG entries (read by every current
// browser), 16 and 32 px, both the small tier.
const images = [await png(master("mark-small.svg"), 16), await png(master("mark-small.svg"), 32)];
const header = Buffer.alloc(6 + 16 * images.length);
header.writeUInt16LE(0, 0);
header.writeUInt16LE(1, 2);
header.writeUInt16LE(images.length, 4);
let offset = header.length;
images.forEach((data, i) => {
  const size = [16, 32][i];
  const entry = 6 + 16 * i;
  header.writeUInt8(size, entry);
  header.writeUInt8(size, entry + 1);
  header.writeUInt16LE(1, entry + 4);
  header.writeUInt16LE(32, entry + 6);
  header.writeUInt32LE(data.length, entry + 8);
  header.writeUInt32LE(offset, entry + 12);
  offset += data.length;
});
writeFileSync(pub("favicon.ico"), Buffer.concat([header, ...images]));

// ---- 3. Lockup PNGs (optional: needs a browser for the live font) ---------
if (process.argv.includes("--lockups")) {
  const { chromium } = await import("playwright");
  const browser = await chromium.launch({ channel: "chromium" });
  const page = await browser.newPage({ deviceScaleFactor: 2 });
  for (const name of Object.keys(masters).filter((n) => n.startsWith("lockup-"))) {
    const svg = master(name).toString();
    await page.setContent(`<!doctype html><body style="margin:0;background:transparent">${svg}</body>`);
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(300);
    await page.locator("svg").first().screenshot({ path: design(`png/${name.replace(".svg", "@2x.png")}`), omitBackground: true });
  }
  await browser.close();
}

// ---- 4. The Open Graph card (optional, also a browser) ---------------------
// public/marketing/og.png, 1200×630: the lockup, the product line and the
// dashboard screenshot (its main area; the sidebar is cropped off).
if (process.argv.includes("--og")) {
  const { chromium } = await import("playwright");
  const browser = await chromium.launch({ channel: "chromium" });
  const page = await browser.newPage({ viewport: { width: 1200, height: 630 } });
  const shot = readFileSync(pub("marketing/dashboard.png")).toString("base64");
  await page.setContent(`<!doctype html><html><head>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Readex+Pro:wght@500;700&family=Inter:wght@400;500&display=swap">
<style>
body{margin:0;width:1200px;height:630px;overflow:hidden;position:relative;font-family:Inter,sans-serif;
background:radial-gradient(ellipse at 100% 100%,#123a45 0,transparent 55%),linear-gradient(160deg,#13253a,#0c1826)}
.lock{position:absolute;left:72px;top:60px;display:flex;align-items:center;gap:22px}
.lock b{font-family:'Readex Pro';font-weight:700;font-size:60px;color:#f5f7fa;letter-spacing:0}.lock b i{font-style:normal;font-weight:500;color:#37b0b8}
.lock em{font-family:'Readex Pro';font-style:normal;font-weight:700;font-size:30px;color:rgba(245,247,250,.55);margin-inline-start:6px}
h1{position:absolute;left:72px;top:170px;margin:0;font-weight:500;font-size:32px;color:#e8edf3}
p{position:absolute;left:72px;top:222px;margin:0;font-size:24px;color:#8fa3b8}
.url{position:absolute;left:72px;bottom:40px;font-size:24px;color:#37b0b8}
.shot{position:absolute;left:380px;top:290px;width:820px;height:340px;border-radius:14px 0 0 0;overflow:hidden;
box-shadow:0 20px 60px rgba(0,0,0,.45);background:#fff}
.shot img{width:1000px;display:block}
</style></head><body>
<div class="lock">${markSvg({ size: 88 })}<b>Vezano <i>Pro</i></b><em>فيزانو برو</em></div>
<h1>Sales, inventory and receivables in one clear system.</h1>
<p>Offline POS · Batches &amp; expiry · Multi-branch · Arabic &amp; English</p>
<div class="url">vezano.app</div>
<div class="shot"><img src="data:image/png;base64,${shot}"></div>
</body></html>`);
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(300);
  await page.screenshot({ path: pub("marketing/og.png") });
  await browser.close();
}

console.log(`brand assets written: ${Object.keys(masters).length} masters, ${outputs.length + 1} PNGs, favicon.ico`);
