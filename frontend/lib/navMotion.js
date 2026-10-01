// Motion of the navigation bars: the app sidebar and its phone drawer
// (components/AppShell.jsx, components/PlatformShell.jsx,
// components/ui/NavMotion.jsx) and the marketing header
// (components/marketing/Chrome.jsx). The company pages' phone tab bar is a
// Django template with the same rules in its own inline script
// (backend/website/templates/website/_tabbar.html).
//
// The rules of lib/motion.js hold here too: 120–250 ms, transform and
// opacity only (the group and menu heights are the one exception, and they
// move only on a click), nothing delays a click or moves focus, nothing
// loops, and everything is off under prefers-reduced-motion. The app's
// <main> never moves for a nav animation, so the till (/sales) is
// untouched.
//
// Pure: no React, no DOM (tests/navMotion.test.mjs).

export const NAV_MOTION = {
  indicator: 200, // the active-item pill sliding to the new page
  drawerIn: 220, // the phone drawer sliding in from the start edge
  drawerOut: 180, // ...and out (kept mounted this long, inert)
  menuOut: 160, // the marketing phone menu folding up
  menuStep: 25, // stagger between the menu's links
  menuMaxSteps: 5,
  badge: 240, // an attention count that went up
  iconTurn: 240, // a language / theme toggle's icon
};

// How far the page must scroll before a header shows it is over content.
export const SCROLLED_AT = 4;

export function scrolledPast(y, threshold = SCROLLED_AT) {
  const value = Number(y);
  return Number.isFinite(value) && value > threshold;
}

// ---- The sliding active-item indicator ------------------------------------

export function indicatorTransform(y) {
  const value = Number.isFinite(Number(y)) ? Math.round(Number(y) * 100) / 100 : 0;
  return `translate3d(0, ${value}px, 0)`;
}

// Web Animations keyframes for the slide from `fromY` to `toY`, or null when
// there is nothing to slide: no previous place (first paint, or the
// indicator was hidden in a folded group — it then appears where it is) or
// the same place.
export function indicatorKeyframes(fromY, toY) {
  const from = Number(fromY);
  const to = Number(toY);
  if (fromY === null || fromY === undefined || !Number.isFinite(from) || !Number.isFinite(to)) return null;
  if (Math.abs(from - to) < 0.5) return null;
  return [{ transform: indicatorTransform(from) }, { transform: indicatorTransform(to) }];
}

// ---- Attention badges -------------------------------------------------------

// Whether a badge going from `previous` to `next` pops: only a real rise
// seen after the counts first arrived (`settled`), so the counts loading
// with the page — or from the session cache — never pop, and a count
// cleared by opening the page never does either.
export function badgePops(previous, next, settled) {
  if (!settled) return false;
  const a = Number(previous) || 0;
  const b = Number(next) || 0;
  return b > a;
}

// ---- The marketing header -----------------------------------------------------

// A marketing pathname without its language prefix, query, hash or trailing
// slash: "/en/solutions/retail/" -> "/solutions/retail"; "/en/" -> "/".
export function bareMarketingPath(pathname) {
  if (typeof pathname !== "string" || !pathname) return "/";
  let path = pathname.split(/[?#]/, 1)[0] || "/";
  if (path === "/en" || path.startsWith("/en/")) path = path.slice(3) || "/";
  if (path.length > 1) path = path.replace(/\/+$/, "") || "/";
  return path.startsWith("/") ? path : `/${path}`;
}

// Whether the header link to `linkPath` (written for the Arabic root, as in
// NAV_LINKS) is the page being read. A section of a page ("/#contact") is
// never the current page; a guide is under "/guides".
export function isCurrentMarketingLink(pathname, linkPath) {
  if (typeof linkPath !== "string" || linkPath.includes("#")) return false;
  const here = bareMarketingPath(pathname);
  const link = bareMarketingPath(linkPath);
  if (link === "/") return here === "/";
  return here === link || here.startsWith(`${link}/`);
}

// The phone menu's links come in one after another, a short stagger that
// stops growing.
export function menuItemDelay(index) {
  const i = Math.max(0, Math.min(Math.floor(Number(index)) || 0, NAV_MOTION.menuMaxSteps));
  return i * NAV_MOTION.menuStep;
}

export function menuItemStyle(index) {
  return { "--menu-delay": `${menuItemDelay(index)}ms` };
}

// The new icon of a language / theme toggle turns in from a quarter turn
// back, from a little smaller and fainter.
export const ICON_TURN = [
  { transform: "rotate(-90deg) scale(0.7)", opacity: 0.35 },
  { transform: "none", opacity: 1 },
];

// How long something closing stays mounted: none at all under reduced
// motion, so nothing is left on screen that is not animating.
export function exitDuration(ms, reduced) {
  if (reduced) return 0;
  const value = Number(ms);
  return Number.isFinite(value) && value > 0 ? value : 0;
}
