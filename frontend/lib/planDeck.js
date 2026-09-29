// The plan cards on the pricing page (components/marketing/pricing/PlanDeck.jsx):
// the rules that decide how they are laid out, kept pure so they can be
// tested without a browser.
//
//   - one price size for every card: the price figures are sized from the
//     LONGEST one, so "500,000 ج.س" is not set bigger than "2,000,000 ج.س"
//     and the prices sit on one baseline;
//   - the desktop column count;
//   - the carousel (phones and tablets): which card the plan pills mark as
//     current, and how far to scroll to bring a card into place — in either
//     writing direction, without reading scrollLeft (its sign differs
//     between RTL implementations).

import { figureChars } from "./figureFit.js";

// The --figure-chars every price figure uses: the widest of them. Texts
// that are not prices (null, "") do not count; with none the figure keeps
// its default.
export function sharedFigureChars(texts) {
  const list = (texts || []).filter((text) => text !== null && text !== undefined && String(text).trim() !== "");
  if (!list.length) return undefined;
  return Math.max(...list.map(figureChars));
}

// Desktop grid columns for `count` plans: { lg } at 1024–1279, { xl } at
// 1280 and up. Three at most on a laptop, four on a wide screen. Four plans
// on a laptop are two rows of two rather than three and an orphan.
export function deckColumns(count) {
  const n = Math.max(1, Number(count) || 0);
  return { lg: n === 4 ? 2 : Math.min(n, 3), xl: Math.min(n, 4) };
}

// Below 640 every deck of 2+ plans is a carousel; 640–1023 only when there
// are more than two (two sit side by side as a plain grid).
export function carouselAt(count) {
  const n = Number(count) || 0;
  return { phone: n > 1, tablet: n > 2 };
}

// How much of each card is in view (IntersectionObserver ratios, 0–1) →
// the index the pills mark as current: the most visible card. On a tablet
// two cards are fully visible at once; then the one the visitor last
// picked wins if it is one of them, else the first in reading order.
const TIE = 0.05;
export function pickActiveIndex(ratios, preferred = null) {
  const list = (ratios || []).map((value) => (Number.isFinite(value) ? value : 0));
  if (!list.length) return 0;
  const best = Math.max(...list);
  if (best <= 0) return Number.isInteger(preferred) && preferred >= 0 && preferred < list.length ? preferred : 0;
  const tied = list.map((value, index) => (best - value <= TIE ? index : -1)).filter((index) => index >= 0);
  if (Number.isInteger(preferred) && tied.includes(preferred)) return preferred;
  return tied[0];
}

// The horizontal distance to scroll the track by (element.scrollBy) so that
// `card` lands where its scroll-snap-align puts it: centred, or at the
// track's inline start (the right edge in RTL) past `inset` (the
// scroll-padding). Both rects are viewport rects ({ left, right }), so the
// answer is the same whatever sign the browser gives scrollLeft in RTL.
export function scrollDelta({ card, track, align = "center", rtl = false, inset = 0 }) {
  if (!card || !track) return 0;
  if (align === "start") {
    return rtl ? card.right - (track.right - inset) : card.left - (track.left + inset);
  }
  if (align === "end") {
    return rtl ? card.left - (track.left + inset) : card.right - (track.right - inset);
  }
  return (card.left + card.right) / 2 - (track.left + track.right) / 2;
}
