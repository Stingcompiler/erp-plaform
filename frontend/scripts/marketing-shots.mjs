// The marketing screenshots (lib/marketingShots.js): encode raw captures into
// the files the public pages load.
//
//   node scripts/marketing-shots.mjs encode <rawDir>
//
// <rawDir> holds PNG captures named <name>.<language>.<theme>.png, at 1× or
// 2× of SHOT_SIZE (the capture script below writes 2×). Each becomes WebP at
// every SHOT_WIDTHS width it can fill, and each light capture also a JPEG
// (SHOT_SIZE width) for browsers without WebP, in public/marketing/shots/.
//
//   node scripts/marketing-shots.mjs capture <rawDir>
//
// Captures them from a running local copy of the app (never production):
// BASE_URL (default http://127.0.0.1:8000, Django serving frontend/out) and
// a seed_demo owner per language, SHOTS_AR_EMAIL / SHOTS_EN_EMAIL with
// SHOTS_PASSWORD. Those are local test accounts in a throwaway SQLite
// database: create a company (currency SDG) and a Business Owner per
// language, then
//   manage.py seed_demo --owner <ar owner> --scale 2500 --sales 60 --yes
//   manage.py seed_demo --owner <en owner> --lang en --scale 2500 --sales 60 --yes
// 1440×900 CSS pixels at device scale 2, light and dark; then `encode`.
import { mkdirSync, readdirSync, existsSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import sharp from "sharp";

import { SHOTS, SHOT_SIZE, shotFallback, shotFile, shotWidths } from "../lib/marketingShots.js";

const pub = (path) => fileURLToPath(new URL(`../public${path}`, import.meta.url));

// Which screen each shot is, what to wait for, and what to do on it first:
// a cart of five seeded products on the till (their barcodes are
// seed_demo's 629…), the first customer's statement on the debt ledger.
const SCREENS = {
  dashboard: {
    path: "/dashboard/",
    ready: "main h1",
    // The first-run checklist is for the owner, not the picture.
    async prepare(page) {
      const hide = page.getByRole("button", { name: /Hide for now|إخفاء الآن/ });
      if (await hide.count()) await hide.first().click();
      await page.waitForTimeout(400);
    },
  },
  pos: {
    path: "/sales/",
    ready: "main input[placeholder]",
    async prepare(page) {
      const scan = page.locator("main input[placeholder]").first();
      for (const index of [2, 3, 6, 1, 12]) {
        await scan.fill(`629${String(index).padStart(10, "0")}`);
        await scan.press("Enter");
        await page.waitForTimeout(350);
      }
    },
  },
  inventory: { path: "/inventory/", ready: "main table" },
  debts: {
    path: "/debts/",
    ready: "main div.overflow-y-auto > button",
    async prepare(page) {
      await page.locator("main div.overflow-y-auto > button").first().click();
      await page.waitForTimeout(1200);
    },
  },
  users: { path: "/users/", ready: "main table, main li" },
};

async function encode(rawDir) {
  mkdirSync(pub("/marketing/shots"), { recursive: true });
  const report = [];
  for (const file of readdirSync(rawDir).filter((f) => f.endsWith(".png")).sort()) {
    const [name, language, theme] = file.replace(/\.png$/, "").split(".");
    if (!SHOTS[name]) { console.warn(`skip ${file}: not in lib/marketingShots.js`); continue; }
    const src = join(rawDir, file);
    const { width } = await sharp(src).metadata();
    for (const target of shotWidths(name)) {
      if (target > width) { console.warn(`${file}: ${width}px wide, too small for ${target}w`); continue; }
      const out = pub(shotFile(name, language, theme, target));
      const info = await sharp(src).resize({ width: target }).webp({ quality: 80, effort: 6, smartSubsample: true }).toFile(out);
      report.push([out.split("/public")[1], info.size]);
    }
    if (theme === "light") {
      const out = pub(shotFallback(name, language));
      const info = await sharp(src).resize({ width: SHOT_SIZE.width }).flatten({ background: "#ffffff" }).jpeg({ quality: 78, mozjpeg: true }).toFile(out);
      report.push([out.split("/public")[1], info.size]);
    }
  }
  for (const [path, size] of report) console.log(`${String(Math.round(size / 1024)).padStart(5)} KB  ${path}`);
}

async function capture(rawDir) {
  const { chromium } = await import("playwright");
  const base = process.env.BASE_URL || "http://127.0.0.1:8000";
  const password = process.env.SHOTS_PASSWORD;
  if (!password) throw new Error("SHOTS_PASSWORD is not set (a local seed_demo owner's password)");
  mkdirSync(rawDir, { recursive: true });
  const browser = await chromium.launch({ channel: "chromium" });
  try {
    for (const language of ["ar", "en"]) {
      const email = process.env[`SHOTS_${language.toUpperCase()}_EMAIL`];
      if (!email) { console.warn(`no SHOTS_${language.toUpperCase()}_EMAIL: skipping ${language}`); continue; }
      for (const theme of ["light", "dark"]) {
        const context = await browser.newContext({
          viewport: SHOT_SIZE, deviceScaleFactor: 2, colorScheme: theme, reducedMotion: "reduce",
          locale: language === "ar" ? "ar-SD" : "en-US", serviceWorkers: "block",
        });
        // The app reads the language and theme from localStorage (I18nProvider).
        await context.addInitScript(([lang, th]) => {
          localStorage.setItem("erp.language", lang);
          localStorage.setItem("erp.theme", th);
        }, [language, theme]);
        const page = await context.newPage();
        await page.goto(`${base}/login/`);
        await page.fill("input[type=email], input[name=email], input[autocomplete=username]", email);
        await page.fill("input[type=password]", password);
        await Promise.all([page.waitForURL(/dashboard|platform/, { timeout: 30000 }), page.keyboard.press("Enter")]);
        for (const [name, screen] of Object.entries(SCREENS)) {
          if (!SHOTS[name]?.languages.includes(language) || !SHOTS[name].themes.includes(theme)) continue;
          await page.goto(`${base}${screen.path}`, { waitUntil: "networkidle" });
          await page.locator(screen.ready).first().waitFor({ timeout: 20000 });
          await page.waitForTimeout(800);
          if (screen.prepare) await screen.prepare(page);
          await page.mouse.move(0, 0);
          const out = join(rawDir, `${name}.${language}.${theme}.png`);
          await page.screenshot({ path: out });
          console.log(out);
        }
        await context.close();
      }
    }
  } finally {
    await browser.close();
  }
}

const [command, dir] = process.argv.slice(2);
if (!dir || !["encode", "capture"].includes(command)) {
  console.error("usage: node scripts/marketing-shots.mjs encode|capture <rawDir>");
  process.exit(2);
}
if (command === "encode" && !existsSync(dir)) throw new Error(`${dir} does not exist`);
await (command === "encode" ? encode(dir) : capture(dir));
