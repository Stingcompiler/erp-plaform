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
//   - text moves by the line, never by the letter: Arabic letters join, and
//     a word split into letters stops being shaped;
//   - transform, opacity and clip-path only, so nothing moves the layout.

// The home hero: the headline's lines rise from behind their mask, then
// the subtitle, the offline line and the buttons fade up while the
// screenshot opens from an inset clip. All of it within HERO_TOTAL_MS.
export const HERO = {
  fontWaitMs: 500, // the longest the hero waits for its fonts
  line: { delay: 0, step: 70, duration: 520 },
  badge: { delay: 0, duration: 400 },
  subtitle: { delay: 240, duration: 400 },
  offline: { delay: 300, duration: 400 },
  actions: { delay: 360, duration: 400 },
  shot: { delay: 300, duration: 600 },
};
export const HERO_TOTAL_MS = 900;

// CSS custom properties for one hero part (`line` takes its index).
export function heroTiming(part, index = 0) {
  const spec = HERO[part];
  const delay = spec.delay + (spec.step || 0) * index;
  return { "--hero-delay": `${delay}ms`, "--hero-dur": `${spec.duration}ms` };
}

// When the last hero part settles, for a headline of `lines` lines.
export function heroEndMs(lines) {
  const parts = ["badge", "subtitle", "offline", "actions", "shot"].map((part) => HERO[part].delay + HERO[part].duration);
  const lastLine = HERO.line.delay + HERO.line.step * Math.max(0, lines - 1) + HERO.line.duration;
  return Math.max(lastLine, ...parts);
}

// The headline's lines: a phrase each, broken after a colon and before a
// dash, so a line is a unit of meaning at any screen width (a phrase wider
// than the screen wraps inside its own mask). Joined with single spaces the
// lines are the headline again, character for character.
export function headlineLines(text) {
  if (typeof text !== "string" || !text.trim()) return [];
  return text
    .split(/(?<=[:؛])\s+|\s+(?=[—–])/u)
    .map((line) => line.trim())
    .filter(Boolean);
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
