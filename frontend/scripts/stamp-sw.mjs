// Stamps out/sw.js after `next build`:
//   __BUILD__            the per-build id, so each deploy gets its own shell
//                        cache and the previous one is retired on activate;
//   __PRECACHE_ASSETS__  every hashed chunk, stylesheet and font of this
//                        export plus the manifest and icons, so the shell is
//                        complete on first install rather than filled in as
//                        pages happen to be visited.
import { readFileSync, writeFileSync, existsSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const out = fileURLToPath(new URL("../out/", import.meta.url));
const buildIdFile = join(out, "..", ".next", "BUILD_ID");
const build = existsSync(buildIdFile) ? readFileSync(buildIdFile, "utf8").trim() : String(Date.now());

export function listPrecacheAssets(root = out) {
  const walk = (dir) => readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    return statSync(full).isDirectory() ? walk(full) : [full];
  });
  const under = (sub) => (existsSync(join(root, sub)) ? walk(join(root, sub)) : []);
  const files = [
    ...under("_next/static").filter((f) => /\.(js|css|woff2?)$/.test(f)),
    ...under("icons").filter((f) => /\.png$/.test(f)),
    join(root, "manifest.webmanifest"),
  ].filter(existsSync);
  return files.map((f) => "/" + relative(root, f).split("\\").join("/")).sort();
}

const isMain = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isMain) {
  const path = join(out, "sw.js");
  if (!existsSync(path)) { console.error("out/sw.js missing — run next build first"); process.exit(1); }
  const assets = listPrecacheAssets();
  const stamped = readFileSync(path, "utf8")
    .replace("__BUILD__", build)
    .replace("__PRECACHE_ASSETS__", JSON.stringify(assets));
  writeFileSync(path, stamped);
  const bytes = assets.reduce((n, a) => n + statSync(join(out, a)).size, 0);
  console.log(`sw.js stamped with build ${build}: ${assets.length} assets, ${(bytes / 1024).toFixed(0)} KB precached`);
}
