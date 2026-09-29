import assert from "node:assert/strict";
import test from "node:test";

import {
  COUNT_MAX_MS,
  COUNT_MIN_MS,
  canCount,
  countUpDuration,
  easeOutCubic,
  formatFigureAs,
  interpolateFigure,
  parseFigure,
  ringFraction,
  ringGeometry,
  ringOffset,
} from "../lib/motion.js";
import { budgetTotals, subscriptionWindow, uploadProgress } from "../lib/progress.js";
import { figureChars } from "../lib/figureFit.js";
import { formatMoney } from "../lib/money.js";

test("a figure parses into number, decimals, grouping and the text around it", () => {
  assert.deepEqual(parseFigure("615,480.00 ج.س"), {
    prefix: "", number: 615480, decimals: 2, grouped: true, suffix: " ج.س", minus: "-",
  });
  assert.equal(parseFigure("-1,234.50 SDG").number, -1234.5);
  assert.equal(parseFigure("12").number, 12);
  assert.equal(parseFigure(12).decimals, 0);
  assert.equal(parseFigure("45.5%").suffix, "%");
  // Not figures: nothing to count, shown as they are.
  assert.equal(parseFigure("—"), null);
  assert.equal(parseFigure("2026-09-29"), null);
  assert.equal(parseFigure("3 / 5"), null);
  assert.equal(parseFigure("١٢٣"), null);
  assert.equal(parseFigure(null), null);
});

test("an in-between value is written like the target: decimals, grouping, label", () => {
  const shape = parseFigure("1,200,000.00 ج.س");
  assert.equal(formatFigureAs(shape, 1234.5), "1,234.50 ج.س");
  assert.equal(formatFigureAs(shape, 0), "0.00 ج.س");
  assert.equal(formatFigureAs(parseFigure("45%"), 12.4), "12%");
  // A tiny negative never shows as "-0.00".
  assert.equal(formatFigureAs(shape, -0.001), "0.00 ج.س");
  assert.equal(formatFigureAs(parseFigure("-50.00 SDG"), -25), "-25.00 SDG");
  // An ungrouped count stays ungrouped ("1200" items is written as such).
  assert.equal(formatFigureAs(parseFigure("1200"), 1100), "1100");
});

test("counting interpolates from the previous figure (or zero) to the new one", () => {
  const to = formatMoney(1000, { currency: "SDG" });
  assert.equal(interpolateFigure(null, to, 0), "0.00 ج.س");
  assert.equal(interpolateFigure(null, to, 0.5), "500.00 ج.س");
  assert.equal(interpolateFigure(null, to, 1), to);
  assert.equal(interpolateFigure("200.00 ج.س", to, 0.5), "600.00 ج.س");
  assert.equal(interpolateFigure(null, "12", 0.5), "6");
  // Not a figure: shown at once.
  assert.equal(interpolateFigure(null, "—", 0.3), "—");
});

test("counting never grows wider than where it ends, and only between like figures", () => {
  assert.equal(canCount(null, "615,480.00 ج.س", figureChars), true);
  assert.equal(canCount(null, "0.00 ج.س", figureChars), false);
  assert.equal(canCount("12.00 ج.س", "615,480.00 ج.س", figureChars), true);
  // Down from a wider figure: swapped, not counted (the card is sized for
  // the new one).
  assert.equal(canCount("615,480.00 ج.س", "12.00 ج.س", figureChars), false);
  // Same width both ways: fine.
  assert.equal(canCount("900.00 ج.س", "100.00 ج.س", figureChars), true);
  // Different currency, unit or precision: no count.
  assert.equal(canCount("12.00 SDG", "15.00 ج.س", figureChars), false);
  assert.equal(canCount("45%", "45.5%", figureChars), false);
  assert.equal(canCount("—", "12", figureChars), false);
  assert.equal(canCount("12", "12", figureChars), false);
});

test("every in-between figure of an allowed count fits the final width", () => {
  const cases = [[null, 1234567.89], [0.5, 999999.99], [-20, 350], [100, 999]];
  for (const [fromValue, toValue] of cases) {
    const to = formatMoney(toValue, { currency: "SDG" });
    const from = fromValue === null ? null : formatMoney(fromValue, { currency: "SDG" });
    assert.ok(canCount(from, to, figureChars), `${from} → ${to}`);
    for (let i = 0; i <= 50; i += 1) {
      const step = interpolateFigure(from, to, easeOutCubic(i / 50));
      assert.ok(figureChars(step) <= figureChars(to), `${step} wider than ${to}`);
    }
  }
});

test("count duration scales with the jump and stays within 250–600 ms", () => {
  assert.equal(countUpDuration(5, 5), 0);
  assert.equal(countUpDuration(0, 1e12), COUNT_MAX_MS);
  const small = countUpDuration(12, 15);
  const big = countUpDuration(0, 615480);
  assert.ok(small >= COUNT_MIN_MS && small < big, `${small} vs ${big}`);
  assert.ok(big <= COUNT_MAX_MS);
  assert.equal(easeOutCubic(0), 0);
  assert.equal(easeOutCubic(1), 1);
  assert.equal(easeOutCubic(2), 1);
  assert.ok(easeOutCubic(0.5) > 0.5);
});

test("ring math: radius inside the stroke, offset from the fraction", () => {
  const { radius, circumference, center } = ringGeometry(64, 6);
  assert.equal(radius, 29);
  assert.equal(center, 32);
  assert.ok(Math.abs(circumference - 2 * Math.PI * 29) < 1e-9);
  assert.equal(ringOffset(0, 100), 100);
  assert.equal(ringOffset(1, 100), 0);
  assert.equal(ringOffset(0.25, 100), 75);
  assert.equal(ringOffset(3, 100), 0);
  assert.equal(ringFraction(5, 10), 0.5);
  assert.equal(ringFraction(15, 10), 1);
  assert.equal(ringFraction(-1, 10), 0);
  assert.equal(ringFraction(5, 0), 0);
  assert.equal(ringFraction("x", 10), 0);
});

test("subscription window: trial, period and grace, or nothing", () => {
  const now = new Date("2026-09-20T12:00:00Z");
  assert.deepEqual(subscriptionWindow({
    status: "trialing", starts_at: "2026-09-01T00:00:00Z", trial_ends_at: "2026-10-01T00:00:00Z",
  }, now), { kind: "trialing", daysLeft: 11, totalDays: 30, endsAt: "2026-10-01T00:00:00.000Z" });
  const monthly = subscriptionWindow({
    status: "active", starts_at: "2025-01-01T00:00:00Z", period_ends_at: "2026-10-15T00:00:00Z",
    plan: { billing_cycle: "monthly" },
  }, now);
  assert.equal(monthly.totalDays, 30);
  assert.equal(monthly.daysLeft, 25);
  const yearly = subscriptionWindow({
    status: "active", starts_at: "2025-01-01T00:00:00Z", period_ends_at: "2027-01-01T00:00:00Z",
    plan: { billing_cycle: "yearly" },
  }, now);
  assert.equal(yearly.totalDays, 365);
  // A first period shorter than a cycle starts at the subscription start.
  const fresh = subscriptionWindow({
    status: "active", starts_at: "2026-09-10T00:00:00Z", period_ends_at: "2026-09-30T00:00:00Z",
    plan: { billing_cycle: "monthly" },
  }, now);
  assert.equal(fresh.totalDays, 20);
  assert.equal(subscriptionWindow({
    status: "grace", period_ends_at: "2026-09-15T00:00:00Z", grace_ends_at: "2026-09-22T00:00:00Z",
  }, now).daysLeft, 2);
  // Past the end: zero, never negative.
  assert.equal(subscriptionWindow({
    status: "trialing", starts_at: "2026-08-01T00:00:00Z", trial_ends_at: "2026-09-01T00:00:00Z",
  }, now).daysLeft, 0);
  assert.equal(subscriptionWindow({ status: "legacy" }, now), null);
  assert.equal(subscriptionWindow({ status: "trialing", starts_at: "2026-09-01T00:00:00Z" }, now), null);
  assert.equal(subscriptionWindow(null, now), null);
});

test("upload progress counts what left the queue since it was last empty", () => {
  assert.equal(uploadProgress(0, 0), null);
  assert.deepEqual(uploadProgress(10, 4), { sent: 6, total: 10, fraction: 0.6 });
  assert.deepEqual(uploadProgress(10, 0), { sent: 10, total: 10, fraction: 1 });
  // More queued than the recorded peak: the peak catches up, nothing sent.
  assert.deepEqual(uploadProgress(2, 5), { sent: 0, total: 5, fraction: 0 });
});

test("budget totals per kind, a kind with no plan left out", () => {
  assert.deepEqual(budgetTotals([
    { kind: "expense", planned: "1000.00", actual: "250.10" },
    { kind: "expense", planned: "500.00", actual: "600.00" },
    { kind: "revenue", planned: "0.00", actual: "90.00" },
  ]), { expense: { planned: 1500, actual: 850.1 } });
  assert.deepEqual(budgetTotals([]), {});
  assert.deepEqual(budgetTotals(null), {});
});
