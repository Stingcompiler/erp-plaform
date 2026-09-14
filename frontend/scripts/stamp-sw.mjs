// Stamps public/sw.js with a per-build id after `next build`, so each deploy
// gets its own shell cache and the previous one is retired on activate.
import { readFileSync, writeFileSync, existsSync } from "node:fs";

const buildIdFile = new URL("../.next/BUILD_ID", import.meta.url);
const build = existsSync(buildIdFile) ? readFileSync(buildIdFile, "utf8").trim() : String(Date.now());
for (const target of ["out/sw.js"]) {
  const path = new URL(`../${target}`, import.meta.url);
  if (!existsSync(path)) continue;
  writeFileSync(path, readFileSync(path, "utf8").replace("__BUILD__", build));
}
console.log(`sw.js stamped with build ${build}`);
