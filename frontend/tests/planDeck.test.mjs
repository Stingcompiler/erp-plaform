import assert from "node:assert/strict";
import test from "node:test";

import { figureChars } from "../lib/figureFit.js";
import { formatPlanAmount } from "../lib/planCatalog.js";
import { carouselAt, deckColumns, pickActiveIndex, scrollDelta, sharedFigureChars } from "../lib/planDeck.js";

test("every price card uses the size of the longest price", () => {
  const prices = [500000, 200000, 2000000].map((amount) => formatPlanAmount(amount, "SDG", "ar"));
  const shared = sharedFigureChars(prices);
  assert.equal(shared, figureChars("2,000,000 ج.س"));
  assert.ok(shared > figureChars(prices[0]), "the shorter price is not sized on its own");
  // Same in English, and order does not matter.
  const en = [2000000, 500000].map((amount) => formatPlanAmount(amount, "SDG", "en"));
  assert.equal(sharedFigureChars(en), sharedFigureChars([...en].reverse()));
});

test("no price figures: no shared size (the figure keeps its default)", () => {
  assert.equal(sharedFigureChars([]), undefined);
  assert.equal(sharedFigureChars(null), undefined);
  assert.equal(sharedFigureChars(["", null, undefined]), undefined);
  // A short price still gets at least the figure's minimum cell count.
  assert.equal(sharedFigureChars(["5"]), figureChars("5"));
});

test("desktop columns: three on a laptop, four on a wide screen, no orphan", () => {
  assert.deepEqual(deckColumns(1), { lg: 1, xl: 1 });
  assert.deepEqual(deckColumns(2), { lg: 2, xl: 2 });
  assert.deepEqual(deckColumns(3), { lg: 3, xl: 3 });
  assert.deepEqual(deckColumns(4), { lg: 2, xl: 4 });
  assert.deepEqual(deckColumns(5), { lg: 3, xl: 4 });
  assert.deepEqual(deckColumns(0), { lg: 1, xl: 1 });
});

test("carousel: phones from two plans, tablets from three", () => {
  assert.deepEqual(carouselAt(1), { phone: false, tablet: false });
  assert.deepEqual(carouselAt(2), { phone: true, tablet: false });
  assert.deepEqual(carouselAt(3), { phone: true, tablet: true });
});

test("the current pill follows the most visible card", () => {
  assert.equal(pickActiveIndex([1, 0.08, 0]), 0);
  assert.equal(pickActiveIndex([0.1, 0.95, 0.1]), 1);
  assert.equal(pickActiveIndex([0, 0.3, 0.7]), 2);
  // Mid-swipe, half and half: the first in reading order.
  assert.equal(pickActiveIndex([0, 0.5, 0.5]), 1);
});

test("two cards fully in view (tablet): the one the visitor picked, else the first", () => {
  assert.equal(pickActiveIndex([1, 1, 0.1]), 0);
  assert.equal(pickActiveIndex([1, 1, 0.1], 1), 1);
  assert.equal(pickActiveIndex([0, 1, 1], 2), 2, "the last pill at the end of the track");
  assert.equal(pickActiveIndex([0, 1, 1], 0), 1, "a pick that scrolled away no longer wins");
});

test("nothing measured yet: the preferred card, else the first", () => {
  assert.equal(pickActiveIndex([0, 0, 0], 2), 2);
  assert.equal(pickActiveIndex([0, 0, 0]), 0);
  assert.equal(pickActiveIndex([], 3), 0);
  assert.equal(pickActiveIndex([0, 0], 5), 0, "an out-of-range pick is ignored");
  assert.equal(pickActiveIndex([NaN, 0.4]), 1);
});

test("scroll delta centres a card, whatever the direction", () => {
  const track = { left: 0, right: 360 };
  // A card to the right of centre: scroll right (positive).
  assert.equal(scrollDelta({ card: { left: 330, right: 640 }, track }), 305);
  // RTL: the next card sits to the LEFT — a negative delta, which scrollBy
  // applies correctly whatever scrollLeft's sign convention is.
  assert.equal(scrollDelta({ card: { left: -280, right: 30 }, track, rtl: true }), -305);
  assert.equal(scrollDelta({ card: { left: 25, right: 335 }, track }), 0, "already centred");
});

test("scroll delta aligns a card to the inline start past the scroll padding", () => {
  const track = { left: 0, right: 800 };
  // LTR: start is the left edge.
  assert.equal(scrollDelta({ card: { left: 400, right: 752 }, track, align: "start", inset: 24 }), 376);
  // RTL: start is the right edge; a card further left needs a negative delta.
  assert.equal(scrollDelta({ card: { left: 48, right: 400 }, track, align: "start", rtl: true, inset: 24 }), -376);
  assert.equal(scrollDelta({ card: { left: 424, right: 776 }, track, align: "start", rtl: true, inset: 24 }), 0);
  assert.equal(scrollDelta({ card: null, track }), 0);
});
