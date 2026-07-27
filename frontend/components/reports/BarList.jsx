"use client";

import { useI18n } from "../../app/providers/I18nProvider";

const money = (v) =>
  Number(v ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

// A lightweight horizontal bar chart built from divs — no charting dependency.
export default function BarList({ items, valueKey = "value", labelKey = "label", format = money }) {
  const { t } = useI18n();
  const max = items.reduce((m, it) => Math.max(m, Number(it[valueKey] ?? 0)), 0) || 1;
  if (items.length === 0) {
    return <p className="py-6 text-center text-sm text-muted">{t("reports.noData")}</p>;
  }
  return (
    <div className="space-y-2.5">
      {items.map((it, i) => {
        const value = Number(it[valueKey] ?? 0);
        const pct = Math.max(2, Math.round((value / max) * 100));
        return (
          <div key={i} className="flex items-center gap-3">
            <div className="w-40 shrink-0 truncate text-sm text-ink" title={it[labelKey]}>
              {it[labelKey]}
            </div>
            <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-paper">
              <div
                className="h-full rounded-full bg-accent"
                style={{ width: `${pct}%` }}
              />
            </div>
            <div className="tabular w-24 shrink-0 text-end text-sm text-ink">
              {format(value)}
            </div>
          </div>
        );
      })}
    </div>
  );
}
