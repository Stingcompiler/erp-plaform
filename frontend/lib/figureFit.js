// Headline figures that fit their card.
//
// A stat card shows one figure — "615,480.00 ج.س", "12", "—". Big Sudanese
// pound amounts used to wrap inside the card, sometimes between the number
// and "ج.س". The figure now never wraps (see .figure-fit in globals.css) and
// its font size shrinks with its length instead: the CSS divides the card's
// width (100cqi) by the figure's length in "cells" times a cell's width,
// clamped between the tier's minimum and maximum size.
//
// This file only measures the text; the sizing is pure CSS, so the figure is
// right on the first paint and on every resize without a ResizeObserver.

// Below this length the tier's maximum size always wins, so short figures
// ("3", "—") are not blown up past the design size.
const MIN_CELLS = 6;

// Figures are set in the monospaced .tabular face: every digit, comma, point
// and Latin letter is one cell (0.565em in IBM Plex Mono; the CSS allows
// 0.6em). Arabic letters fall back to the Arabic UI face, where an isolated
// letter such as the ج and س of "ج.س" is about 0.95em wide — 1.75 cells.
const ARABIC_CELLS = 1.75;

// Width of the figure in cells. Combining marks (Arabic harakat) take no
// width of their own, so they are not counted.
export function figureChars(text) {
  const raw = text === null || text === undefined ? "" : String(text);
  const visible = raw.normalize("NFC").replace(/\p{M}/gu, "");
  let cells = 0;
  for (const ch of visible) cells += /\p{Script=Arabic}/u.test(ch) ? ARABIC_CELLS : 1;
  return Math.max(MIN_CELLS, cells);
}

// "615,480.00 ج.س" → ["615,480.00", "ج.س"]: a money figure's number and its
// currency label, so the label — whole — can drop under the number on a card
// too narrow even at the smallest size, instead of the line breaking inside
// the number or overflowing the card. Anything else (a count, a word, a
// percentage) is one piece: null.
const MONEY_FIGURE = /^([-+−]?[\d,]+(?:\.\d+)?)\s+(\S+)$/u;

export function splitFigure(text) {
  if (typeof text !== "string") return null;
  const match = text.trim().match(MONEY_FIGURE);
  return match ? [match[1], match[2]] : null;
}

// The inline style that feeds the length to .figure-fit__value.
export function figureFitStyle(text) {
  return { "--figure-chars": figureChars(text) };
}
