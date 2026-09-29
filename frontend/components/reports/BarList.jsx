"use client";

import { useEffect, useState } from "react";

import { useI18n } from "../../app/providers/I18nProvider";
import { formatAmount } from "@/lib/money";
import { prefersReducedMotion } from "@/lib/useReducedMotionSafe";

const money = (v) =>
  formatAmount(v);

// Stable keys by label, so a product's bar is the same element in March and
// in April and moves to its new length (.bar-morph) instead of being
// redrawn. Two rows with one label get #2, #3… in their order.
function keysFor(items, labelKey) {
  const seen = new Map();
  return items.map((it) => {
    const label = String(it[labelKey] ?? "");
    const n = (seen.get(label) || 0) + 1;
    seen.set(label, n);
    return `${label}#${n}`;
  });
}

// A lightweight horizontal bar chart built from divs — no charting dependency.
// Bars grow from the start on first paint and move between periods; under
// reduced motion they are drawn at their length at once.
export default function BarList({ items, valueKey = "value", labelKey = "label", format = money }) {
  const { t } = useI18n();
  // Drawn at full length from the first frame when motion is reduced;
  // otherwise from zero, two frames later (the zero width has to be laid
  // out once for the transition to start from it).
  const [grown, setGrown] = useState(() => typeof window === "undefined" || prefersReducedMotion());
  useEffect(() => {
    if (grown) return undefined;
    let inner = 0;
    const outer = requestAnimationFrame(() => { inner = requestAnimationFrame(() => setGrown(true)); });
    return () => { cancelAnimationFrame(outer); cancelAnimationFrame(inner); };
  }, [grown]);
  const max = items.reduce((m, it) => Math.max(m, Number(it[valueKey] ?? 0)), 0) || 1;
  if (items.length === 0) {
    return <p className="py-6 text-center text-sm text-muted">{t("reports.noData")}</p>;
  }
  const keys = keysFor(items, labelKey);
  return (
    <div className="space-y-2.5">
      {items.map((it, i) => {
        const value = Number(it[valueKey] ?? 0);
        const pct = Math.max(2, Math.round((value / max) * 100));
        return (
          <div key={keys[i]} className="flex items-center gap-3">
            <div className="w-28 shrink-0 truncate text-sm text-ink sm:w-40" title={it[labelKey]}>
              {it[labelKey]}
            </div>
            <div className="bar-track h-2.5 flex-1 overflow-hidden rounded-full bg-paper">
              <div
                className="bar-morph h-full rounded-full bg-accent"
                style={{ width: grown ? `${pct}%` : "0%" }}
              />
            </div>
            <div className="tabular min-w-20 shrink-0 whitespace-nowrap text-end text-sm text-ink">
              {format(value)}
            </div>
          </div>
        );
      })}
    </div>
  );
}
