// Vezano Pro («فيزانو برو») advertising poster series — 4 posters × 4 formats
// (+ a light variant of the main poster), in Arabic (RTL, the primary set) and
// English (LTR, files end in -en). README.md in this folder has the plan.
//
//   node design/marketing/posters/generate.mjs              both languages: 40 PNGs + A4 PDFs + 2 contact sheets
//   node design/marketing/posters/generate.mjs --lang=en    one language only (ar | en)
//   node design/marketing/posters/generate.mjs story main   only formats/posters whose names match
//
// HTML → Playwright Chromium screenshot, like frontend/scripts/brand-icons.mjs
// --og. Needs frontend/node_modules (playwright + chromium, sharp) and a network
// connection: Readex Pro / Tajawal / Inter come from Google Fonts, the QR
// encoder (qrcode-generator) and decoder (jsQR) from cdn.jsdelivr.net.
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

import { markSvg } from "../../../frontend/lib/brandMark.js";

const require = createRequire(new URL("../../../frontend/package.json", import.meta.url));
const { chromium } = require("playwright");
const sharp = require("sharp");

const here = (p) => fileURLToPath(new URL(p, import.meta.url));
const shotPath = (name) => here(`../../../frontend/public/marketing/${name}.png`);
const SHOTS = Object.fromEntries(
  ["dashboard", "dashboard-dark", "pos", "pos-dark", "debts", "users"].map((n) => [
    n,
    `data:image/png;base64,${readFileSync(shotPath(n)).toString("base64")}`,
  ]),
);

const REGISTER_URL = "https://vezano.app/register/";
const QR_LIB = "https://cdn.jsdelivr.net/npm/qrcode-generator@1.4.4/qrcode.js";
const JSQR_LIB = "https://cdn.jsdelivr.net/npm/jsqr@1.4.0/dist/jsQR.js";
// The English set needs heavier Inter weights (its body text is Inter).
const FONTS = {
  ar: "https://fonts.googleapis.com/css2?family=Readex+Pro:wght@500;700&family=Tajawal:wght@400;500;700;800&family=Inter:wght@400;500;600&display=block",
  en: "https://fonts.googleapis.com/css2?family=Readex+Pro:wght@500;700&family=Inter:wght@400;500;600;700;800&display=block",
};

// ---- formats ----------------------------------------------------------------
// A4 is laid out at 1240×1754 CSS px and captured at device scale 2 →
// 2480×3508 (300 dpi). The PDF prints the same page at 210×297 mm.
const FORMATS = {
  story: { w: 1080, h: 1920, scale: 1 },
  square: { w: 1080, h: 1080, scale: 1 },
  landscape: { w: 1200, h: 628, scale: 1 },
  a4: { w: 1240, h: 1754, scale: 2 },
};

// ---- language ---------------------------------------------------------------
// L is the language being rendered. Arabic is the primary set (RTL); English
// mirrors the layout (LTR) and swaps the copy. tx(ar, en) picks one.
let L = "ar";
const tx = (ar, en) => (L === "en" ? en : ar);
const COPY = {
  ar: {
    cta: "ابدأ تجربتك المجانية — 14 يومًا", sameDay: "تفعيل في نفس اليوم", scan: "امسح للتسجيل",
    pos: "نقطة البيع", branches: ["الخرطوم", "أم درمان", "بحري"], hub: "الإدارة ترى الكل",
    offline: "دون اتصال: البيع مستمر", online: "عاد الاتصال: تمت المزامنة",
  },
  en: {
    cta: "Start your free trial — 14 days", sameDay: "Activated the same day", scan: "Scan to sign up",
    pos: "Point of sale", branches: ["Khartoum", "Omdurman", "Bahri"], hub: "Head office sees all",
    offline: "Offline: still selling", online: "Back online: synced",
  },
};
const C = () => COPY[L];

// Overlays sit on the side the text column is not: mirror left/right in the
// English (LTR) layouts. Arabic styles pass through untouched.
function m(style = "") {
  if (L !== "en") return style.replace(/^=/, "");
  if (style.startsWith("=")) return style.slice(1); // "=" keeps a style as is
  return style
    .replace(/inset:(\S+) (\S+) (\S+) ([^;]+)/, "inset:$1 $4 $3 $2")
    .replace(/\bleft:/g, "@L@").replace(/\bright:/g, "left:").replace(/@L@/g, "right:");
}

// ---- small parts ------------------------------------------------------------
const ICON = {
  check: '<svg viewBox="0 0 24 24"><path d="M6 12.5l4 4L18 8" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  wifiOff:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 8.8a15 15 0 0 1 4.2-2.6M10.7 5.1A15 15 0 0 1 22 8.8M5 12.5a10 10 0 0 1 5.2-2.7M15.4 10.4A10 10 0 0 1 19 12.5M8.5 16a5 5 0 0 1 7 0"/><circle cx="12" cy="19.5" r=".9" fill="currentColor"/><path d="M3 3l18 18"/></svg>',
  sync: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 11a8 8 0 0 0-14.3-4.9L4 8"/><path d="M4 4v4h4"/><path d="M4 13a8 8 0 0 0 14.3 4.9L20 16"/><path d="M20 20v-4h-4"/></svg>',
  arrow: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M19 12H5M11 6l-6 6 6 6"/></svg>',
};

const lockup = () =>
  `<div class="lockup">${markSvg({ size: 64 })}<b>${tx("فيزانو <i>برو</i>", "Vezano <i>Pro</i>")}</b></div>`;

const url = (text = "vezano.app") => `<span class="url" dir="ltr">${text}</span>`;

const headline = (p) =>
  `<h1${p.headline[1] ? ' class="two"' : ""}><span>${p.headline[0]}</span>${p.headline[1] ? `<span class="acc">${p.headline[1]}</span>` : ""}</h1>`;

const points = (list) =>
  `<ul class="points">${list.map((t) => `<li><span class="tick">${ICON.check}</span><span>${t}</span></li>`).join("")}</ul>`;

const chips = (list) => `<div class="chips">${list.map((t) => `<span>${t}</span>`).join("")}</div>`;

// A browser window with a screenshot. The screenshot fills the window (cover),
// `pos` picks the crop, `zoom` (>1) magnifies it.
function browser(shot, { style, pos = "100% 0%", zoom = 0 } = {}) {
  const size = zoom ? `${zoom * 100}% auto` : "cover";
  return `<div class="browser" style="${m(style)}">
  <div class="bar"><i></i><i></i><i></i><span dir="ltr">vezano.app</span></div>
  <div class="shot" style="background-image:url(${SHOTS[shot]});background-size:${size};background-position:${pos}"></div>
</div>`;
}

// A phone showing the POS payment panel (x 22–402 of the 1440-wide shot).
function phone(shot, style) {
  return `<div class="phone" style="${m(style)}"><div class="scr">
  <div class="phead"><span>${C().pos}</span><em></em></div>
  <div class="pshot"><img src="${SHOTS[shot]}" alt=""></div>
</div></div>`;
}

// Poster 2: branches converge into the hub — the logo's idea, as a diagram.
function branchDiagram(style = "") {
  const nodes = [110, 320, 530].map((x, i) => [x, C().branches[i]]);
  const hub = { x: 320, y: 300, s: 150 };
  const top = hub.y - hub.s / 2;
  const tile = 58, gap = 12, t0 = hub.x - tile - gap / 2, t1 = hub.x + gap / 2, u0 = hub.y - tile - gap / 2, u1 = hub.y + gap / 2;
  return `<div class="diagram" style="${m(style)}"><svg viewBox="0 0 640 440">
  ${nodes.map(([x]) => `<path d="M${x} 130 L${hub.x + (x - hub.x) * 0.28} ${top + 4}" stroke="var(--ink)" stroke-width="9" stroke-linecap="round"/>`).join("")}
  ${nodes.map(([x, n]) => `<circle cx="${x}" cy="130" r="26" fill="#a3e3e6"/><text x="${x}" y="72" text-anchor="middle">${n}</text>`).join("")}
  <rect x="${hub.x - hub.s / 2}" y="${top}" width="${hub.s}" height="${hub.s}" rx="34" fill="#0e7c86"/>
  <rect x="${t0}" y="${u0}" width="${tile}" height="${tile}" rx="12" fill="#fff"/>
  <rect x="${t1}" y="${u0}" width="${tile}" height="${tile}" rx="12" fill="#a3e3e6"/>
  <rect x="${t0}" y="${u1}" width="${tile}" height="${tile}" rx="12" fill="#a3e3e6"/>
  <rect x="${t1}" y="${u1}" width="${tile}" height="${tile}" rx="12" fill="#fff"/>
  <text class="hub" x="${hub.x}" y="${hub.y + hub.s / 2 + 52}" text-anchor="middle">${C().hub}</text>
</svg></div>`;
}

// Poster 3: "offline → synced".
function syncMotif(style = "", vertical = false) {
  return `<div class="motif${vertical ? " vert" : ""}" style="${m(style)}">
  <span class="st off">${ICON.wifiOff}<span>${C().offline}</span></span>
  <span class="ar">${ICON.arrow}</span>
  <span class="st on">${ICON.sync}<span>${C().online}</span></span>
</div>`;
}

// Poster 4: a bank-app transfer, recorded by hand and matched to the statement.
function transferCard(style = "") {
  if (L === "en")
    return `<div class="transfer" style="${m(style)}">
  <div class="th"><b>Transfer recorded</b><span class="ok">${ICON.check}Matched to statement</span></div>
  <dl>
    <div><dt>App</dt><dd>Bankak</dd></div>
    <div><dt>Transaction no.</dt><dd dir="ltr">20931847</dd></div>
    <div><dt>Amount</dt><dd><bdi dir="ltr">150,000.00</bdi> SDG</dd></div>
  </dl>
</div>`;
  return `<div class="transfer" style="${style}">
  <div class="th"><b>تحويل بنكي مسجّل</b><span class="ok">${ICON.check}مطابَق مع الكشف</span></div>
  <dl>
    <div><dt>التطبيق</dt><dd>بنكك</dd></div>
    <div><dt>رقم العملية</dt><dd dir="ltr">20931847</dd></div>
    <div><dt>المبلغ</dt><dd><bdi dir="ltr">150,000.00</bdi> ج.س</dd></div>
  </dl>
</div>`;
}

// ---- the four posters -------------------------------------------------------
const modules = () =>
  tx(
    ["المبيعات", "المخزون", "المشتريات", "العملاء", "الموظفون", "الإدارة المالية"],
    ["Sales", "Inventory", "Purchasing", "Customers", "Staff", "Financial management"],
  );

const POSTERS = {
  "01-main": {
    themes: ["dark", "light"],
    get headline() {
      return tx(["نظام واحد يدير متجرك بكل فروعه"], ["One system for your whole business\u00a0— every branch"]);
    },
    body(fmt) {
      const offline = `<p class="note">${ICON.wifiOff}<span>${tx("ويستمر حتى مع انقطاع الشبكة", "Keeps selling when the network drops")}</span></p>`;
      // The one English line of the Arabic set (the English set needs none).
      const en = tx(`<p class="en" dir="ltr">Vezano Pro — one system for every branch: ERP + POS, Arabic first.</p>`, "");
      const line = `<p class="sub">${modules().join("\u00a0· ")}</p>`;
      if (fmt === "square" || fmt === "landscape") return `${line}${offline}`;
      return `${chips(modules())}${offline}${en}`;
    },
    visual(fmt, theme) {
      const dash = theme === "light" ? "dashboard" : "dashboard-dark";
      const pos = theme === "light" ? "pos" : "pos-dark";
      if (fmt === "story")
        return browser(dash, { style: "inset:0 0 12% 0" }) + phone(pos, "=left:-2%;bottom:0;height:62%");
      if (fmt === "square") return browser(dash, { style: "inset:0", zoom: 1.45, pos: "100% 86%" });
      if (fmt === "landscape")
        return browser(dash, { style: "left:0;top:0;right:0;bottom:0" }) + phone(pos, "left:4%;bottom:-8%;height:70%");
      return browser(dash, { style: "inset:0 0 8% 8%" }) + phone(pos, "left:0;bottom:0;height:66%");
    },
  },
  "02-branches": {
    themes: ["dark"],
    get headline() {
      return tx(["كل فروعك في مكان واحد", "وكل موظف يرى ما يخصّه"], ["All your branches in one place", "each person sees what’s theirs"]);
    },
    get list() {
      return tx(
        ["كل فرع يرى بياناته، والإدارة ترى الكل", "12 دورًا بصلاحيات واضحة", "موافقات للخصم واعتماد الورديات", "سجل لكل عملية"],
        ["Each branch sees its own data; head office sees everything", "12 roles with clear permissions", "Approvals for discounts and till shifts", "A log of every action"],
      );
    },
    body(fmt) {
      return points(fmt === "square" ? this.list.slice(0, 3) : this.list);
    },
    visual(fmt) {
      if (fmt === "story")
        return branchDiagram("left:0;right:0;top:0;height:40%") + browser("users", { style: "left:0;right:0;bottom:0;height:54%", pos: "100% 0%" });
      if (fmt === "square") return branchDiagram("inset:0");
      if (fmt === "landscape")
        return browser("users", { style: "left:0;right:0;bottom:0;height:57%", pos: "100% 0%" }) + branchDiagram("left:12%;right:12%;top:0;height:37%");
      return branchDiagram("right:0;top:0;bottom:0;width:38%") + browser("users", { style: "left:0;top:4%;bottom:4%;width:60%", pos: "100% 0%" });
    },
  },
  "03-offline": {
    themes: ["dark"],
    get headline() {
      return tx(["البيع ما بيقف", "حتى لو قطعت الشبكة أو الكهرباء"], ["Selling never stops", "even when the network or power goes out"]);
    },
    get list() {
      return tx(
        ["الكاشير يبيع ويحصّل دون إنترنت", "كل العمليات تُحفظ وتُزامَن مرة واحدة عند عودة الاتصال", "بلا تكرار ولا ضياع"],
        ["The till sells and collects payments offline", "Everything is saved and synced once when you’re back online", "No duplicates, nothing lost"],
      );
    },
    body() {
      return points(this.list);
    },
    visual(fmt) {
      if (fmt === "story")
        return syncMotif("top:0;left:0;right:0") + browser("pos-dark", { style: "left:0;right:0;bottom:0;top:15%" });
      if (fmt === "square") return syncMotif("top:0;left:0;right:0") + browser("pos-dark", { style: "left:0;right:0;bottom:0;top:34%", zoom: 1.3, pos: "0% 62%" });
      if (fmt === "landscape")
        return browser("pos-dark", { style: "inset:0" }) + syncMotif("left:-4%;bottom:5%;font-size:19px", true);
      return browser("pos-dark", { style: "top:0;bottom:6%;left:10%;right:0" }) + syncMotif("left:0;bottom:0;font-size:30px", true);
    },
  },
  "04-bankak": {
    themes: ["dark"],
    get headline() {
      return tx(["بنكك والتطبيقات البنكية…", "مسجّلة ومطابَقة"], ["Bankak and <b style=\"font-weight:inherit;white-space:nowrap\">bank-app</b> payments", "recorded and matched"]);
    },
    get list() {
      return tx(
        ["سجّل التحويل برقم العملية", "طابِق كشف الحساب بضغطة", "دفتر ديون يعرف من يدين لك ومنذ متى"],
        ["Record each transfer with its transaction number", "Match your bank statement in one click", "A debt ledger that knows who owes you and since when"],
      );
    },
    body() {
      return points(this.list);
    },
    visual(fmt) {
      if (fmt === "story") return browser("debts", { style: "inset:0 0 10% 0" }) + transferCard("left:0;bottom:0;width:62%");
      if (fmt === "square") return browser("debts", { style: "top:0;bottom:0;right:0;left:30%", zoom: 1.9, pos: "88% 7%" }) + transferCard("left:0;top:50%;transform:translateY(-50%);width:52%");
      if (fmt === "landscape") return browser("debts", { style: "inset:0" }) + transferCard("left:-3%;bottom:6%;width:72%");
      return browser("debts", { style: "inset:0 0 10% 6%" }) + transferCard("left:0;bottom:0;width:52%");
    },
  },
};

// ---- themes & CSS -------------------------------------------------------------
const THEME = {
  dark: {
    bg: "radial-gradient(90% 60% at 100% 0%, rgba(55,176,184,.20), transparent 60%), radial-gradient(80% 60% at 0% 100%, rgba(14,124,134,.26), transparent 62%), #0f1d2c",
    ink: "#f5f7fa", muted: "#a9bccd", acc: "#37b0b8", pro: "#37b0b8",
    ctaBg: "#37b0b8", ctaInk: "#08161f", chip: "rgba(55,176,184,.12)", chipLine: "rgba(55,176,184,.38)",
    card: "#16283b", cardLine: "rgba(255,255,255,.10)", frame: "#0b1520", shadow: "0 30px 80px rgba(0,0,0,.55)",
  },
  light: {
    bg: "radial-gradient(90% 60% at 100% 0%, rgba(14,124,134,.12), transparent 60%), radial-gradient(80% 60% at 0% 100%, rgba(55,176,184,.16), transparent 62%), #f5f7fa",
    ink: "#12253b", muted: "#4a5d70", acc: "#0e7c86", pro: "#0e7c86",
    ctaBg: "#0e7c86", ctaInk: "#ffffff", chip: "rgba(14,124,134,.08)", chipLine: "rgba(14,124,134,.30)",
    card: "#ffffff", cardLine: "rgba(18,37,59,.10)", frame: "#e6ebf1", shadow: "0 30px 70px rgba(18,37,59,.22)",
  },
};

// Per-format sizes: u scales the frames/cards; the rest are type sizes.
const SIZES = {
  story: { u: 1, pad: "96px 80px 88px", mark: 88, word: 58, h1: 88, h1two: 76, sub: 38, pt: 38, note: 36, en: 26 },
  square: { u: 0.8, pad: "68px 72px 64px", mark: 64, word: 44, h1: 64, h1two: 58, sub: 34, pt: 34, note: 34, en: 22 },
  landscape: { u: 0.62, pad: "48px 56px 44px", mark: 52, word: 34, h1: 42, h1two: 40, sub: 23, pt: 23, note: 22, en: 17 },
  a4: { u: 1.1, pad: "104px 104px 96px", mark: 92, word: 60, h1: 84, h1two: 76, sub: 34, pt: 36, note: 34, en: 24 },
};

function css(fmt, theme) {
  const t = THEME[theme];
  const s = SIZES[fmt];
  const { w, h } = FORMATS[fmt];
  return `
@page{size:210mm 297mm;margin:0}
*{box-sizing:border-box;margin:0;padding:0}
html,body{width:${w}px;height:${h}px;overflow:hidden}
body{--u:${s.u};--ink:${t.ink};--muted:${t.muted};--acc:${t.acc};font-family:Tajawal,sans-serif;color:${t.ink};background:${t.bg};
  -webkit-print-color-adjust:exact;print-color-adjust:exact}
.page{position:relative;width:100%;height:100%;padding:${s.pad};display:flex;flex-direction:column}
.lockup{display:flex;align-items:center;gap:${s.mark * 0.3}px}
.lockup svg{width:${s.mark}px;height:${s.mark}px;flex:none}
.lockup b{font-family:'Readex Pro';font-weight:700;font-size:${s.word}px;line-height:1;color:${t.ink};white-space:nowrap}
.lockup b i{font-style:normal;font-weight:500;color:${t.pro}}
.url{font-family:Inter,sans-serif;font-weight:600;color:${t.acc};letter-spacing:.01em}
h1{font-family:'Readex Pro';font-weight:700;font-size:${s.h1}px;line-height:1.28;letter-spacing:0;text-wrap:balance;color:${t.ink}}
h1 span{display:block;text-wrap:balance}h1 .acc{color:${t.acc}}
h1.two{font-size:${s.h1two || s.h1}px}
.sub{font-size:${s.sub}px;font-weight:500;line-height:1.55;color:${t.muted};text-wrap:balance}
.chips{display:flex;flex-wrap:wrap;gap:${s.sub * 0.36}px}
.chips span{font-size:${s.sub}px;font-weight:700;line-height:1;padding:${s.sub * 0.42}px ${s.sub * 0.62}px ${s.sub * 0.36}px;border-radius:999px;background:${t.chip};border:1.5px solid ${t.chipLine};color:${t.ink}}
.note{display:flex;align-items:center;gap:${s.note * 0.4}px;font-size:${s.note}px;font-weight:700;color:${t.acc}}
.note svg{width:${s.note * 1.1}px;height:${s.note * 1.1}px;flex:none}
.en{font-family:Inter,sans-serif;font-size:${s.en}px;color:${t.muted};opacity:.85;text-align:right}
.points{list-style:none;display:flex;flex-direction:column;gap:${s.pt * 0.42}px}
.points li{display:flex;align-items:flex-start;gap:${s.pt * 0.42}px;font-size:${s.pt}px;font-weight:500;line-height:1.4;color:${t.ink}}
.points .tick{flex:none;width:${s.pt * 1.05}px;height:${s.pt * 1.05}px;margin-top:${s.pt * 0.12}px;border-radius:50%;background:${t.ctaBg};color:${t.ctaInk};display:grid;place-items:center}
.points .tick svg{width:72%;height:72%}
.visual{position:relative;flex:1;min-height:0}
.browser{position:absolute;border-radius:calc(var(--u)*22px);overflow:hidden;background:${t.frame};box-shadow:${t.shadow};border:1px solid ${t.cardLine}}
.browser .bar{position:absolute;top:0;left:0;right:0;height:calc(var(--u)*44px);display:flex;align-items:center;gap:calc(var(--u)*9px);padding:0 calc(var(--u)*20px);direction:ltr;background:${t.frame}}
.browser .bar i{width:calc(var(--u)*13px);height:calc(var(--u)*13px);border-radius:50%;background:${theme === "dark" ? "#2a3c50" : "#c9d3de"}}
.browser .bar span{margin:0 auto;transform:translateX(calc(var(--u)*-30px));font:500 calc(var(--u)*17px) Inter,sans-serif;color:${t.muted};padding:calc(var(--u)*5px) calc(var(--u)*40px);border-radius:999px;background:${theme === "dark" ? "#16283b" : "#f5f7fa"}}
.browser .shot{position:absolute;top:calc(var(--u)*44px);left:0;right:0;bottom:0;background-repeat:no-repeat}
.phone{position:absolute;aspect-ratio:.54;container-type:size;border-radius:calc(var(--u)*50px);padding:calc(var(--u)*12px);background:${theme === "dark" ? "#22354a" : "#12253b"};box-shadow:${t.shadow},inset 0 0 0 1px rgba(255,255,255,.12)}
.phone .scr{width:100%;height:100%;border-radius:calc(var(--u)*39px);overflow:hidden;display:flex;flex-direction:column;background:${theme === "dark" ? "#0b1520" : "#f5f7fa"}}
.phead{flex:none;height:12%;display:flex;align-items:flex-end;justify-content:space-between;padding:0 13cqw 3cqw;font:700 9cqw Tajawal,sans-serif;color:${t.ink}}
.phead em{width:5cqw;height:5cqw;border-radius:50%;background:#37b0b8;box-shadow:0 0 0 2cqw rgba(55,176,184,.25)}
.pshot{flex:1;position:relative;overflow:hidden}
.pshot img{position:absolute;left:0;top:0;width:378.9%;transform:translate(-1.53%,-32.8%)}
.diagram{position:absolute;display:flex;justify-content:center}
.diagram svg{height:100%;width:100%;overflow:visible}
.diagram text{font:700 30px Tajawal,sans-serif;fill:${t.ink}}
.diagram text.hub{fill:${t.acc};font-size:28px}
.motif{position:absolute;display:flex;align-items:center;justify-content:center;gap:calc(var(--u)*16px);font-size:calc(var(--u)*30px);font-weight:700}
.motif .st{display:flex;align-items:center;gap:.4em;padding:.5em .8em .45em;border-radius:999px;white-space:nowrap}
.motif .st svg{width:1.15em;height:1.15em;flex:none}
.motif .off{background:rgba(244,178,90,.12);color:#f4b25a;border:1.5px solid rgba(244,178,90,.45)}
.motif .on{background:rgba(55,176,184,.14);color:#5fd0d6;border:1.5px solid rgba(55,176,184,.5)}
.motif .ar{color:${t.muted};display:flex}.motif .ar svg{width:1.3em;height:1.3em}
.motif.vert{flex-direction:column;align-items:flex-start;gap:.35em;padding:.7em;border-radius:1.2em;background:rgba(11,21,32,.92);box-shadow:${t.shadow};border:1px solid ${t.cardLine}}
.motif.vert .ar{transform:rotate(-90deg);margin-inline-start:.9em}
.transfer{position:absolute;background:${t.card};border:1px solid ${t.cardLine};border-radius:calc(var(--u)*24px);box-shadow:${t.shadow};padding:calc(var(--u)*30px) calc(var(--u)*34px);font-size:calc(var(--u)*27px)}
.transfer .th{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:.4em .6em;margin-bottom:.7em}
.transfer .th b{font-weight:800;font-size:1.08em;white-space:nowrap}
.transfer .ok{display:flex;align-items:center;gap:.25em;font-size:.82em;font-weight:700;color:#5fd0d6;background:rgba(55,176,184,.14);border:1.5px solid rgba(55,176,184,.5);padding:.3em .6em .25em;border-radius:999px;white-space:nowrap}
.transfer .ok svg{width:1.1em;height:1.1em}
.transfer dl{display:flex;flex-direction:column;gap:.5em}
.transfer dl div{display:flex;justify-content:space-between;gap:1em;padding-top:.5em;border-top:1px solid ${t.cardLine}}
.transfer dt{color:${t.muted};font-weight:500}.transfer dd{font-weight:700}
.transfer dd[dir=ltr],.transfer bdi{font-family:Inter,sans-serif;font-weight:600}
.cta{display:inline-flex;align-items:center;justify-content:center;border-radius:999px;background:${t.ctaBg};color:${t.ctaInk};font-weight:800;white-space:nowrap}
.muted{color:${t.muted}}
${L === "en" ? `
body{font-family:Inter,sans-serif}
h1{line-height:1.14;letter-spacing:-.018em}
.lockup b{letter-spacing:-.01em}
.sub{line-height:1.45}
.points li>span:last-child{text-wrap:pretty}
.phead{font-family:Inter,sans-serif;font-size:8cqw}
.diagram text{font-family:Inter,sans-serif;font-size:27px}.diagram text.hub{font-size:26px}
.motif .ar svg{transform:scaleX(-1)}
.motif.vert .ar{transform:rotate(90deg)}
.cta{font-weight:700}
.transfer .th b{font-weight:700}` : ""}
`;
}

// ---- layouts, one per format ---------------------------------------------------
function layout(fmt, key, theme) {
  const p = POSTERS[key];
  const body = p.body(fmt);
  const vis = `<div class="visual">${p.visual(fmt, theme)}</div>`;
  if (fmt === "story")
    return `<div class="page">
  <header style="display:flex;justify-content:space-between;align-items:center">${lockup()}</header>
  <div style="margin-top:92px">${headline(p)}</div>
  <div style="margin-top:44px;display:flex;flex-direction:column;gap:30px">${body}</div>
  <div style="margin-top:64px;flex:1;min-height:0;display:flex;flex-direction:column">${vis}</div>
  <footer style="margin-top:72px;display:flex;flex-direction:column;align-items:stretch;gap:26px">
    <span class="cta" style="height:124px;font-size:44px">${C().cta}</span>
    <div style="display:flex;justify-content:space-between;align-items:center;font-size:36px;font-weight:700">
      <span class="muted">${C().sameDay}</span>${url().replace("class=\"url\"", 'class="url" style="font-size:40px"')}
    </div>
  </footer>
</div>`;
  if (fmt === "square")
    return `<div class="page">
  <header style="display:flex;justify-content:space-between;align-items:center">${lockup()}${url().replace("class=\"url\"", 'class="url" style="font-size:34px"')}</header>
  <div style="margin-top:48px">${headline(p)}</div>
  <div style="margin-top:28px;display:flex;flex-direction:column;gap:18px">${body}</div>
  <div style="margin-top:40px;flex:1;min-height:0;display:flex;flex-direction:column">${vis}</div>
  <footer style="margin-top:44px;display:flex;justify-content:space-between;align-items:center;gap:24px">
    <span class="cta" style="height:92px;padding:0 ${tx(44, 36)}px;font-size:${tx(36, 34)}px">${C().cta}</span>
    <span class="muted" style="font-size:34px;font-weight:700;${tx("white-space:nowrap", "line-height:1.2;text-align:right;text-wrap:balance")}">${C().sameDay}</span>
  </footer>
</div>`;
  if (fmt === "landscape")
    return `<div class="page" style="flex-direction:row;gap:40px">
  <div style="flex:0 0 580px;display:flex;flex-direction:column">
    ${lockup()}
    <div style="margin-top:30px">${headline(p)}</div>
    <div style="margin-top:18px;display:flex;flex-direction:column;gap:12px">${body}</div>
    <div style="flex:1"></div>
    <footer style="display:flex;align-items:center;gap:22px">
      <span class="cta" style="height:60px;padding:0 28px;font-size:23px">${C().cta}</span>
      <span style="display:flex;flex-direction:column;gap:4px;font-size:19px;font-weight:700;white-space:nowrap"><span class="muted">${C().sameDay}</span>${url().replace("class=\"url\"", 'class="url" style="font-size:21px"')}</span>
    </footer>
  </div>
  <div style="flex:1;display:flex;flex-direction:column;padding:10px 0 4px">${vis}</div>
</div>`;
  // A4 print: ≥10 mm safe margins everywhere (104 CSS px ≈ 17.6 mm), a QR to
  // the registration page in the footer band.
  return `<div class="page">
  <header style="display:flex;justify-content:space-between;align-items:center">${lockup()}${url().replace("class=\"url\"", 'class="url" style="font-size:36px"')}</header>
  <div style="margin-top:80px">${headline(p)}</div>
  <div style="margin-top:40px;display:flex;flex-direction:column;gap:26px">${body}</div>
  <div style="margin-top:64px;flex:1;min-height:0;display:flex;flex-direction:column">${vis}</div>
  <footer class="band" style="margin-top:64px;display:flex;align-items:center;gap:48px;padding:40px 44px;border-radius:36px;background:${THEME[theme].card};border:1px solid ${THEME[theme].cardLine}">
    <div style="flex:1;display:flex;flex-direction:column;gap:16px">
      <span style="font-family:'Readex Pro';font-weight:700;font-size:44px;line-height:1.3;white-space:nowrap">${C().cta}</span>
      <span class="muted" style="font-size:32px;font-weight:700">${C().sameDay}</span>
      ${url("vezano.app/register").replace("class=\"url\"", 'class="url" style="font-size:40px;text-align:${tx("right", "left")}"')}
    </div>
    <div style="display:flex;flex-direction:column;align-items:center;gap:12px">
      <div id="qr" style="width:252px;height:252px;background:#fff;border-radius:18px;padding:14px"></div>
      <span class="muted" style="font-size:24px;font-weight:700">${C().scan}</span>
    </div>
  </footer>
</div>`;
}

function html(fmt, key, theme) {
  return `<!doctype html><html lang="${L}" dir="${tx("rtl", "ltr")}"><head><meta charset="utf-8">
<link rel="stylesheet" href="${FONTS[L]}">
${fmt === "a4" ? `<script src="${QR_LIB}"></script>` : ""}
<style>${css(fmt, theme)}</style></head><body>${layout(fmt, key, theme)}
${fmt === "a4" ? `<script>
  const qr = qrcode(0, "M"); qr.addData(${JSON.stringify(REGISTER_URL)}); qr.make();
  const n = qr.getModuleCount(), q = 2, size = n + q * 2; let d = "";
  for (let r = 0; r < n; r++) for (let c = 0; c < n; c++) if (qr.isDark(r, c)) d += "M" + (c + q) + " " + (r + q) + "h1v1h-1z";
  document.getElementById("qr").innerHTML = '<svg viewBox="0 0 ' + size + ' ' + size + '" width="100%" height="100%" shape-rendering="crispEdges"><path d="' + d + '" fill="#0f1d2c"/></svg>';
</script>` : ""}
</body></html>`;
}

// ---- render -----------------------------------------------------------------------
const langArg = process.argv.find((a) => a.startsWith("--lang="));
const LANGS = langArg ? [langArg.slice(7)] : ["ar", "en"];
const filters = process.argv.slice(2).filter((a) => !a.startsWith("--"));
const wanted = (fmt, key) => filters.length === 0 || filters.every((f) => fmt.includes(f) || key.includes(f));
const out = (p) => here(`out/${p}`);

const browserApp = await chromium.launch({ channel: "chromium" });
const rendered = [];

async function settle(page) {
  const want = L === "en"
    ? [['700 40px "Readex Pro"', "Vezano"], ['500 40px "Readex Pro"', "Pro"], ["500 30px Inter", "Sales"], ["700 30px Inter", "Sales"], ["600 20px Inter", "vezano.app"]]
    : [['700 40px "Readex Pro"', "فيزانو"], ['500 40px "Readex Pro"', "برو"], ["500 30px Tajawal", "المبيعات"], ["700 30px Tajawal", "المبيعات"], ["800 30px Tajawal", "ابدأ"], ["500 20px Inter", "vezano.app"], ["600 20px Inter", "vezano.app"]];
  await page.evaluate(async (want) => {
    await Promise.all(want.map(([f, t]) => document.fonts.load(f, t)));
    await document.fonts.ready;
  }, want);
  // Fail loudly if a font did not load (the page would fall back silently).
  const missing = await page.evaluate((want) => want.filter(([f, t]) => !document.fonts.check(f, t)).map(([f]) => f), want);
  if (missing.length) throw new Error(`fonts not loaded: ${missing.join(", ")}`);
  await page.waitForTimeout(150);
}

const suffix = () => (L === "en" ? "-en" : "");
for (const lang of LANGS) {
L = lang;
const qrChecks = [];
for (const [fmt, f] of Object.entries(FORMATS)) {
  for (const [key, p] of Object.entries(POSTERS)) {
    for (const theme of p.themes) {
      if (!wanted(fmt, key)) continue;
      const page = await browserApp.newPage({ viewport: { width: f.w, height: f.h }, deviceScaleFactor: f.scale });
      await page.setContent(html(fmt, key, theme), { waitUntil: "networkidle" });
      await settle(page);
      // Layout guard: nothing may spill out of the page or its safe area.
      const problems = await page.evaluate(({ w, h, safe }) => {
        const bad = [];
        for (const el of document.querySelectorAll("h1,p,li,.chips span,.cta,.lockup,.url,footer,.muted")) {
          const r = el.getBoundingClientRect();
          if (r.width === 0) continue;
          if (r.left < safe - 0.5 || r.top < safe - 0.5 || r.right > w - safe + 0.5 || r.bottom > h - safe + 0.5)
            bad.push(`${el.tagName}.${el.className} "${el.textContent.trim().slice(0, 24)}" at ${Math.round(r.left)},${Math.round(r.top)}–${Math.round(r.right)},${Math.round(r.bottom)}`);
          if (el.scrollWidth > el.clientWidth + 1 && getComputedStyle(el).overflow !== "visible") bad.push(`overflow ${el.tagName}`);
        }
        const v = document.querySelector(".visual").getBoundingClientRect();
        if (v.height < 120) bad.push(`visual too small (${Math.round(v.height)}px)`);
        return bad;
      }, { w: f.w, h: f.h, safe: fmt === "a4" ? 59 : 24 });
      if (problems.length) console.warn(`! ${fmt}/${key}-${theme}${suffix()}:\n  ${problems.join("\n  ")}`);
      mkdirSync(out(fmt), { recursive: true });
      const png = out(`${fmt}/${key}-${theme}${suffix()}.png`);
      const buf = await page.screenshot({ type: "png" });
      await sharp(buf).png({ compressionLevel: 9, palette: false }).toFile(png);
      rendered.push({ fmt, key, theme, png });
      if (fmt === "a4") {
        // QR region, in device pixels, for the decode check below.
        const box = await page.locator("#qr").boundingBox();
        qrChecks.push({ name: `${key}-${theme}${suffix()}`, png, box });
        // The page is laid out at 1240 CSS px; A4 is 793.7 CSS px wide at
        // 96 dpi, so zoom the whole page down for print (text stays vector).
        // Big blurred box-shadows come out as hard dark rectangles in some PDF
        // viewers (macOS Preview), so the PDF drops them.
        await page.addStyleTag({ content: `html{zoom:${793.7 / 1240}}.browser,.phone,.transfer,.motif.vert{box-shadow:none!important}` });
        await page.emulateMedia({ media: "print" });
        await page.pdf({
          path: out(`a4/${key}-${theme}${suffix()}.pdf`), width: "210mm", height: "297mm", printBackground: true,
          margin: { top: 0, right: 0, bottom: 0, left: 0 }, pageRanges: "1",
        });
      }
      await page.close();
      console.log(`✓ ${fmt}/${key}-${theme}${suffix()}`);
    }
  }
}

// ---- QR check: decode each A4 PNG's QR with jsQR ---------------------------------
if (qrChecks.length) {
  const page = await browserApp.newPage();
  await page.setContent(`<script src="${JSQR_LIB}"></script>`, { waitUntil: "networkidle" });
  const lines = [];
  for (const { name, png, box } of qrChecks) {
    const pad = 40;
    const { data, info } = await sharp(png)
      .extract({ left: Math.round(box.x * 2) - pad, top: Math.round(box.y * 2) - pad, width: Math.round(box.width * 2) + pad * 2, height: Math.round(box.height * 2) + pad * 2 })
      .ensureAlpha().raw().toBuffer({ resolveWithObject: true });
    const text = await page.evaluate(
      ({ b64, w, h }) => {
        const bytes = Uint8ClampedArray.from(atob(b64), (c) => c.charCodeAt(0));
        const r = jsQR(bytes, w, h);
        return r ? r.data : null;
      },
      { b64: data.toString("base64"), w: info.width, h: info.height },
    );
    const ok = text === REGISTER_URL;
    lines.push(`${name}: ${ok ? "OK" : "FAIL"} → ${text}`);
    if (!ok) process.exitCode = 1;
  }
  writeFileSync(out(`qr-check${suffix()}.txt`), `QR decode check (jsQR on the rendered A4 PNGs), expecting ${REGISTER_URL}\n${lines.join("\n")}\n`);
  console.log(lines.join("\n"));
  await page.close();
}

// ---- contact sheet (only after a full run) -----------------------------------------
if (filters.length === 0) {
  const ROW_H = 330;
  const rows = Object.entries(POSTERS).flatMap(([key, p]) => p.themes.map((theme) => ({ key, theme })));
  const cells = await Promise.all(
    rows.flatMap(({ key, theme }) =>
      Object.entries(FORMATS).map(async ([fmt, f]) => {
        const width = Math.round((f.w / f.h) * ROW_H);
        const b = await sharp(out(`${fmt}/${key}-${theme}${suffix()}.png`)).resize({ width, height: ROW_H }).jpeg({ quality: 82 }).toBuffer();
        return `<figure><img src="data:image/jpeg;base64,${b.toString("base64")}" width="${width}" height="${ROW_H}"><figcaption>${fmt}/${key}-${theme}${suffix()}</figcaption></figure>`;
      }),
    ),
  );
  const perRow = Object.keys(FORMATS).length;
  const rowsHtml = rows.map((_, i) => `<div class="row">${cells.slice(i * perRow, (i + 1) * perRow).join("")}</div>`).join("");
  const page = await browserApp.newPage({ viewport: { width: 1640, height: 800 } });
  await page.setContent(`<!doctype html><html><head><style>
body{margin:0;padding:36px;background:#e9edf2;font:500 15px Inter,system-ui,sans-serif;color:#12253b}
h2{margin:0 0 20px;font-size:22px}.row{display:flex;gap:22px;margin-bottom:22px;align-items:flex-end}
figure{margin:0;flex:none}figcaption{font-size:14px;white-space:nowrap;width:0}img{display:block;border-radius:6px;box-shadow:0 4px 14px rgba(18,37,59,.2)}figcaption{margin-top:6px}
</style></head><body><h2>Vezano Pro — poster series${tx("", ", English")} (20 images)</h2>${rowsHtml}</body></html>`);
  await page.screenshot({ path: out(`contact-sheet${suffix()}.png`), fullPage: true });
  await page.close();
  console.log(`✓ contact-sheet${suffix()}.png`);
}
} // for each language

await browserApp.close();
