// The app's motion vocabulary, in one place.
//
// Motion here is feedback, not decoration: a tab indicator that follows the
// click, a figure that counts to its new value, a ring that fills to a real
// number, a check that confirms a sale or an approval, bars that move to the
// new period instead of blinking. Every one of them:
//
//   - is short (150–250 ms for interface changes; counting and chart morphs
//     up to COUNT_MAX_MS, because the eye has to follow a number);
//   - uses the same curve (EASE) or spring (SPRING);
//   - is off — the end state, drawn at once — under
//     `prefers-reduced-motion: reduce` (lib/useReducedMotionSafe.js; the CSS
//     side is the reduce rule in app/globals.css);
//   - never holds input: nothing waits for an animation to finish.
//
// This file is pure (no React, no DOM) so the math is tested in node
// (tests/motion.test.mjs). The hooks live in lib/useReducedMotionSafe.js
// and lib/useCountUp.js.

export const DURATION = {
  fast: 0.15, // content cross-fade, hover
  base: 0.2, // indicator slide, check circle
  slow: 0.25, // check stroke
  chart: 0.35, // bars moving to a new period
};

// One easing everywhere: a quick start that settles ("emphasised
// decelerate"). CSS twin: --motion-ease in globals.css.
export const EASE = [0.2, 0, 0, 1];
export const EASE_CSS = "cubic-bezier(0.2, 0, 0, 1)";

// The spring for things that follow the pointer (the tab indicator).
// Critically damped enough not to wobble past the tab it lands on.
export const SPRING = { type: "spring", stiffness: 520, damping: 42, mass: 0.8 };

export const TRANSITION = { duration: DURATION.base, ease: EASE };

// The side a bar grows from and a horizontal move starts at. In Arabic the
// start is the right edge: a bar filling from the left reads backwards.
export function inlineStart(dir) {
  return dir === "rtl" ? "right" : "left";
}

// ---- Counting figures ------------------------------------------------------

export const COUNT_MIN_MS = 250;
export const COUNT_MAX_MS = 600;

export function easeOutCubic(t) {
  const x = Math.min(1, Math.max(0, t));
  return 1 - (1 - x) ** 3;
}

// How long a count takes: longer for a bigger jump (orders of magnitude,
// so 12 → 15 and 12 → 1,200,000 both read), never past COUNT_MAX_MS.
export function countUpDuration(from, to) {
  const delta = Math.abs(Number(to) - Number(from));
  if (!Number.isFinite(delta) || delta === 0) return 0;
  const scale = Math.min(1, Math.log10(1 + delta) / 6);
  return Math.round(COUNT_MIN_MS + (COUNT_MAX_MS - COUNT_MIN_MS) * scale);
}

// "615,480.00 ج.س" → { prefix: "", number: 615480, decimals: 2,
// grouped: true, suffix: " ج.س" }. Only Latin digits count (the app writes
// every figure in them, lib/money.js); the text around the number may not
// hold digits, so a date ("2026-09-29") or a ratio ("3 / 5") is not a
// countable figure — it is shown as it is.
const FIGURE = /^([^\d]*?)([-−]?)(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?([^\d]*)$/u;

export function parseFigure(text) {
  if (typeof text === "number") text = String(text);
  if (typeof text !== "string") return null;
  const match = text.match(FIGURE);
  if (!match) return null;
  const [, prefix, sign, whole, fraction = "", suffix] = match;
  if (/[-−]$/u.test(prefix)) return null;
  const digits = whole.replace(/,/g, "");
  const number = Number(`${digits}${fraction ? `.${fraction}` : ""}`) * (sign ? -1 : 1);
  if (!Number.isFinite(number)) return null;
  return {
    prefix,
    number,
    decimals: fraction.length,
    grouped: whole.includes(","),
    suffix,
    minus: sign || "-",
  };
}

const formatters = new Map();
function formatterFor(decimals, grouped) {
  const key = `${decimals}:${grouped}`;
  if (!formatters.has(key)) {
    formatters.set(key, new Intl.NumberFormat("en-US", {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
      useGrouping: grouped,
    }));
  }
  return formatters.get(key);
}

// A number written the way `shape` (a parsed figure) writes its own: the
// same decimals, the same grouping, the same text around it. Grouping is
// kept when the target has none only because it is too small to need one:
// "999" counting to "1,200" groups from 1,000 on.
export function formatFigureAs(shape, value) {
  const rounded = Number(value.toFixed(shape.decimals));
  const grouped = shape.grouped || Math.abs(shape.number) < 1000;
  const body = formatterFor(shape.decimals, grouped).format(Math.abs(rounded));
  const negative = rounded < 0 && body.replace(/[0.,]/g, "") !== "";
  return `${shape.prefix}${negative ? shape.minus : ""}${body}${shape.suffix}`;
}

// The figure `progress` (0..1, already eased) of the way from `from` to
// `to`, written like `to`. `from` null (first paint) counts from zero.
export function interpolateFigure(from, to, progress) {
  const target = parseFigure(to);
  if (!target) return to;
  if (progress >= 1) return to;
  const start = from === null || from === undefined ? 0 : parseFigure(from)?.number ?? 0;
  return formatFigureAs(target, start + (target.number - start) * progress);
}

// Whether `from` may count to `to` in place. Both must be figures of the
// same kind (same currency label, same unit), and the count may never be
// wider than where it ends: a card sized for "12.00 ج.س" must not show
// "615,480.00 ج.س" on the way down. Such a change is swapped, not counted.
export function canCount(from, to, widthOf) {
  const target = parseFigure(to);
  if (!target) return false;
  if (from === null || from === undefined) return target.number !== 0;
  const origin = parseFigure(from);
  if (!origin) return false;
  if (origin.prefix !== target.prefix || origin.suffix !== target.suffix) return false;
  if (origin.decimals !== target.decimals) return false;
  if (origin.number === target.number) return false;
  if (widthOf && widthOf(from) > widthOf(to)) return false;
  return true;
}

// ---- Progress rings --------------------------------------------------------

// A ring of `size` px with a `stroke` px band: the radius sits in the middle
// of the band so the stroke never clips at the viewBox edge.
export function ringGeometry(size, stroke) {
  const radius = (size - stroke) / 2;
  return { radius, circumference: 2 * Math.PI * radius, center: size / 2 };
}

// 0..1 of the way `value` is to `max`; nothing sensible (no max, negative
// max, not a number) is 0, and over the top is a full ring.
export function ringFraction(value, max) {
  const v = Number(value);
  const m = Number(max);
  if (!Number.isFinite(v) || !Number.isFinite(m) || m <= 0) return 0;
  return Math.min(1, Math.max(0, v / m));
}

// stroke-dashoffset for `fraction` of the circle drawn.
export function ringOffset(fraction, circumference) {
  return circumference * (1 - Math.min(1, Math.max(0, fraction)));
}

// ---- Moving between app pages -----------------------------------------------
//
// The workspace content (the shell's <main>) fades in and rises a few pixels
// when the route changes (lib/useRouteEnter.js). Enter only: the old page is
// gone at once, nothing waits for an exit, and the new page takes clicks and
// keys from its first frame. Transform and opacity only, so no layout shift.
export const ROUTE_ENTER = { duration: 180, distance: 6 };

// Routes whose content never moves on arrival: the till (/sales opens on the
// POS), where nothing may move between a scan and the next.
export const ROUTE_ENTER_SKIP = ["/sales"];

function routeOf(pathname) {
  if (typeof pathname !== "string" || !pathname) return "";
  const path = pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
  return path || "/";
}

// Whether arriving at `to` from `from` plays the route entrance: not on
// first paint (no `from`), not for the same page (a trailing slash, a query
// or hash change), and never onto a skipped route.
export function routeEnterApplies(from, to) {
  const a = routeOf(from);
  const b = routeOf(to);
  if (!a || !b || a === b) return false;
  return !ROUTE_ENTER_SKIP.some((skip) => b === skip || b.startsWith(`${skip}/`));
}

// Web Animations keyframes for the entrance.
export function routeEnterKeyframes(distance = ROUTE_ENTER.distance) {
  return [
    { opacity: 0, transform: `translateY(${distance}px)` },
    { opacity: 1, transform: "none" },
  ];
}

// ---- Cards entering a page ---------------------------------------------------
//
// A page's cards rise in on first load with a short stagger (.enter-rise in
// globals.css). The stagger stops growing, so the last card is in place
// within ENTER.duration + ENTER.step × ENTER.maxSteps.
export const ENTER = { duration: 200, step: 40, maxSteps: 5 };

export function enterDelay(index) {
  const i = Math.max(0, Math.min(Math.floor(Number(index)) || 0, ENTER.maxSteps));
  return i * ENTER.step;
}

export function enterStyle(index) {
  return { "--enter-delay": `${enterDelay(index)}ms` };
}

// ---- A value that changed ----------------------------------------------------
//
// The next { value, count } when a watched value becomes `value`: the count
// goes up only for a real change between two known values, so a value that
// arrives with the first load (nothing → "Pro") or goes away is not one.
export function countChange(state, value) {
  const known = (v) => v !== null && v !== undefined && v !== "";
  const changed = known(state.value) && known(value) && !Object.is(state.value, value);
  return { value, count: state.count + (changed ? 1 : 0) };
}

// ---- Public site (marketing pages) -----------------------------------------
//
// The marketing pages use the same curve (--motion-ease) with a little more
// room: an entrance is read once, not on every click. Three rules on top of
// the ones above:
//
//   - content is never hidden in the HTML. A pre-animation state only
//     applies once a script has armed it (the `motion-ok` class on <html>
//     for the hero, `data-reveal-state` on a card), so a crawler, a no-JS
//     visitor or a failed script gets the page as it is;
//   - the home page's headline does not move at all: it is whole and
//     readable in the first painted frame (landing review 2026-09-29 — the
//     old per-phrase mask left it clipped at first paint on a slow phone);
//   - transform, opacity and clip-path only, so nothing moves the layout.

// The home hero, around the static headline and badge: the subtitle, offline
// line and buttons rise a few pixels from a dimmed start and the screenshot
// settles from a hair smaller. Nothing starts hidden (HERO_START_OPACITY)
// and nothing waits for a font, so the first frame already shows every
// part; the whole entrance is over within HERO_TOTAL_MS.
export const HERO = {
  subtitle: { delay: 0, duration: 360 },
  offline: { delay: 40, duration: 360 },
  actions: { delay: 80, duration: 360 },
  shot: { delay: 120, duration: 480 },
};
export const HERO_TOTAL_MS = 600;
export const HERO_START_OPACITY = 0.4;

// CSS custom properties for one hero part.
export function heroTiming(part) {
  const spec = HERO[part];
  return { "--hero-delay": `${spec.delay}ms`, "--hero-dur": `${spec.duration}ms` };
}

// When the last hero part settles.
export function heroEndMs() {
  return Math.max(...Object.values(HERO).map((spec) => spec.delay + spec.duration));
}

// Section cards fading up as they scroll in (lib/useRevealOnce.js).
export const REVEAL = { duration: 250, step: 40, maxSteps: 5, distance: 12 };

// The delay of the `index`-th card in a group: a short stagger that stops
// growing, so the eighth card does not wait a third of a second.
export function revealDelay(index) {
  const i = Math.max(0, Math.min(Number(index) || 0, REVEAL.maxSteps));
  return i * REVEAL.step;
}

export function revealStyle(index) {
  return { "--reveal-delay": `${revealDelay(index)}ms` };
}
