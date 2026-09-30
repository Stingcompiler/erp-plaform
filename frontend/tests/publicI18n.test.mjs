import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { CATALOG, translate } from "../lib/i18n.js";
import { PUBLIC_CATALOG, translatePublic } from "../lib/publicI18n.js";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");

// Every module the public pages load: app/(marketing) and what it imports,
// plus the root layout they share with the app.
function publicModules() {
  const entries = [];
  const walk = (dir) => {
    for (const name of readdirSync(dir)) {
      const path = join(dir, name);
      if (statSync(path).isDirectory()) walk(path);
      else if (/\.(js|jsx)$/.test(name)) entries.push(path);
    }
  };
  walk(join(root, "app/(marketing)"));
  entries.push(join(root, "app/layout.js"), join(root, "components/HtmlShell.jsx"));
  const seen = new Set();
  const resolveImport = (from, spec) => {
    let base;
    if (spec.startsWith("@/")) base = join(root, spec.slice(2));
    else if (spec.startsWith(".")) base = resolve(dirname(from), spec);
    else return null;
    for (const candidate of [base, `${base}.js`, `${base}.jsx`, join(base, "index.js")]) {
      if (existsSync(candidate) && statSync(candidate).isFile()) return candidate;
    }
    return null;
  };
  const visit = (file) => {
    if (seen.has(file)) return;
    seen.add(file);
    const source = readFileSync(file, "utf8");
    for (const match of source.matchAll(/(?:import|export)[^'"]*?from\s*["']([^"']+)["']|import\(\s*["']([^"']+)["']\s*\)/g)) {
      const target = resolveImport(file, match[1] || match[2]);
      if (target) visit(target);
    }
  };
  entries.forEach(visit);
  return [...seen].map((file) => relative(root, file));
}

test("the public pages never load the app's dictionary", () => {
  const modules = publicModules();
  assert.ok(modules.includes("lib/publicI18n.js"));
  assert.ok(!modules.includes("lib/i18n.js"), "lib/i18n.js is reachable from a public page");
  for (const heavy of ["lib/improvementsI18n.js", "lib/debtI18n.js", "lib/subscriptionI18n.js", "lib/labelsI18n.js"]) {
    assert.ok(!modules.includes(heavy), heavy);
  }
});

test("every key a public page names is in the public catalog", () => {
  const missing = [];
  let checked = 0;
  for (const file of publicModules()) {
    if (/I18n\.js$/.test(file)) continue;
    const source = readFileSync(join(root, file), "utf8");
    for (const match of source.matchAll(/["'`]([a-z][A-Za-z0-9]*(?:\.[A-Za-z0-9_-]+)+)["'`]/g)) {
      const key = match[1];
      if (translate("en", key) === key) continue; // not a catalog key
      checked += 1;
      for (const lang of ["en", "ar"]) if (translatePublic(lang, key) === key) missing.push(`${lang} ${key} (${file})`);
    }
    // t(`pricing.limitLabels.${key}`): the whole group must be there.
    for (const match of source.matchAll(/\bt\(\s*`([a-z][A-Za-z0-9]*(?:\.[A-Za-z0-9_]+)*)\.\$\{/g)) {
      const prefix = match[1];
      if (typeof translate("en", prefix) !== "object") continue;
      checked += 1;
      if (typeof translatePublic("en", prefix) !== "object") missing.push(`group ${prefix} (${file})`);
    }
  }
  assert.ok(checked > 150, `only ${checked} keys found`);
  assert.deepEqual(missing, []);
});

test("each public string is the app catalog's string", () => {
  const walk = (publicNode, appNode, path) => {
    if (publicNode && typeof publicNode === "object" && !Array.isArray(publicNode)) {
      for (const [key, value] of Object.entries(publicNode)) walk(value, appNode?.[key], `${path}.${key}`);
    } else {
      assert.deepEqual(publicNode, appNode, path);
    }
  };
  for (const lang of ["en", "ar"]) walk(PUBLIC_CATALOG[lang], CATALOG[lang], lang);
});
