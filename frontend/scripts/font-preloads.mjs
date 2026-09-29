// Runs after `next build`: keeps only the font preloads each exported page's
// language needs.
//
// The fonts are declared once, in the root layout every page shares
// (app/fonts/fonts.js), so next/font preloads the same nine files on every
// page: Tajawal on English pages, Inter and Sora on Arabic ones, IBM Plex
// Mono everywhere. On a slow line those preloads compete with the stylesheet
// and delay the first paint (landing review 2026-09-29: 177–208 KB of fonts
// on a 500 kbps connection). This keeps, per page, the text faces only:
//
//   ar  Tajawal (Arabic: 400, 500, 700)
//   en  Inter + Sora (Latin)
//
// Readex Pro draws nothing but the 18 px wordmark: preloading it (23 KB
// Arabic, 31 KB Latin) pushed the first paint on the review's slow
// profile from ~3.75 s to ~4.0 s, so it swaps in from its @font-face
// (fallback: the bold display face). No mono (reference numbers only). Nothing else
// changes: every @font-face stays, so any text still gets its face — a face
// that is not preloaded simply starts downloading when the page uses it.
// The same hints are dropped from the inline RSC payload of each HTML page
// and from its index.txt (client-side navigation), or React would add them
// back after hydration.
import { readFileSync, readdirSync, statSync, writeFileSync, existsSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const out = fileURLToPath(new URL("../out/", import.meta.url));

export const KEEP = {
  ar: [["Tajawal", "arabic"]],
  en: [["Inter", "latin"], ["Sora", "latin"]],
};

// url → { family, subset } for every preloadable (.p.woff2) face in the CSS.
export function preloadFaces(css) {
  const faces = new Map();
  for (const match of css.matchAll(/@font-face\{([^}]*)\}/g)) {
    const body = match[1];
    const url = body.match(/url\((\/_next\/static\/media\/[^)]+\.p\.woff2)\)/)?.[1];
    if (!url) continue;
    const family = body.match(/font-family:\s*['"]?([^;'"]+)['"]?/)?.[1]?.trim();
    // The subset by where its range starts: the minifier writes Google's
    // "U+0600-06FF, …" as "u+06??,…" and "U+0000-00FF, …" as "u+00??,…".
    const range = (body.match(/unicode-range:([^;}]*)/)?.[1] || "").trim().toLowerCase();
    const subset = /^u\+06(00|\?\?)/.test(range) ? "arabic" : /^u\+(0000-00ff|00\?\?)/.test(range) ? "latin" : "other";
    faces.set(url, { family, subset });
  }
  return faces;
}

export function keepFor(language, faces) {
  const wanted = KEEP[language] || KEEP.ar;
  return new Set([...faces].filter(([, face]) => wanted.some(([family, subset]) => face.family === family && face.subset === subset)).map(([url]) => url));
}

// The page's text with every font preload not in `keep` removed.
export function prune(text, keep, kind) {
  const drop = (url) => url.endsWith(".p.woff2") && !keep.has(url);
  if (kind === "txt") {
    return text.replace(/^:HL\["(\/_next\/static\/media\/[^"]+)","font",\{[^}]*\}\]\n/gm, (row, url) => (drop(url) ? "" : row));
  }
  return text
    .replace(/<link rel="preload" href="(\/_next\/static\/media\/[^"]+)" as="font"[^>]*\/>/g, (tag, url) => (drop(url) ? "" : tag))
    .replace(/:HL\[\\"(\/_next\/static\/media\/[^\\]+)\\",\\"font\\",\{[^}]*\}\]\\n/g, (row, url) => (drop(url) ? "" : row));
}

function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    if (name === "_next") return [];
    return statSync(full).isDirectory() ? walk(full) : [full];
  });
}

function main() {
  const cssDir = join(out, "_next/static/css");
  if (!existsSync(cssDir)) throw new Error("no out/_next/static/css — run next build first");
  const faces = new Map();
  for (const file of readdirSync(cssDir).filter((f) => f.endsWith(".css"))) {
    for (const [url, face] of preloadFaces(readFileSync(join(cssDir, file), "utf8"))) faces.set(url, face);
  }
  const keep = { ar: keepFor("ar", faces), en: keepFor("en", faces) };
  if (keep.ar.size < 3 || keep.en.size < 2) throw new Error(`font faces not recognised: ${JSON.stringify([...faces])}`);
  let pages = 0;
  let removed = 0;
  for (const file of walk(out)) {
    const path = "/" + relative(out, file).split("\\").join("/");
    const kind = file.endsWith(".html") ? "html" : file.endsWith(".txt") ? "txt" : null;
    if (!kind) continue;
    const text = readFileSync(file, "utf8");
    if (!text.includes(".p.woff2")) continue;
    const htmlLang = kind === "html" ? text.match(/<html[^>]*\slang="(\w+)"/)?.[1] : null;
    const language = htmlLang || (path.startsWith("/en/") ? "en" : "ar");
    const next = prune(text, keep[language] || keep.ar, kind);
    if (next !== text) {
      removed += (text.match(/\.p\.woff2/g) || []).length - (next.match(/\.p\.woff2/g) || []).length;
      writeFileSync(file, next);
      pages += 1;
    }
  }
  console.log(`font preloads: kept ${keep.ar.size} (ar) / ${keep.en.size} (en) of ${faces.size} files; ${removed} hints removed from ${pages} files`);
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) main();
