"use client";

import { useI18n } from "../../app/providers/I18nProvider";

// What the plan allows against what the company actually has — the same
// counters the server enforces at create/sign-in, so a full bar here means
// the next attempt is refused there.
export const USAGE_KEYS = ["devices", "users", "branches", "warehouses"];

export function usageTone(cell) {
  if (!cell || cell.limit == null) return "muted";
  if (cell.used > cell.limit) return "danger";
  if (cell.used >= cell.limit) return "warn";
  return "ok";
}

export default function UsageMeter({ usage, compact = false }) {
  const { t } = useI18n();
  if (!usage) return null;
  return (
    <div className={compact ? "grid gap-2 sm:grid-cols-2" : "space-y-3"}>
      {USAGE_KEYS.filter((key) => usage[key]).map((key) => {
        const cell = usage[key];
        const tone = usageTone(cell);
        const pct = cell.limit ? Math.min(100, Math.round((cell.used / cell.limit) * 100)) : 0;
        const bar = { ok: "bg-ok", warn: "bg-warn", danger: "bg-danger", muted: "bg-ink/20" }[tone];
        return (
          <div key={key}>
            <div className="flex items-baseline justify-between text-sm">
              <span>{t(`usage.${key}`)}</span>
              <span dir="ltr" className={`tabular font-semibold ${tone === "danger" ? "text-danger" : ""}`}>
                {cell.used}
                <span className="text-muted"> / {cell.limit == null ? t("usage.unlimited") : cell.limit}</span>
              </span>
            </div>
            <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-line">
              <div className={`h-full ${bar}`} style={{ width: cell.limit == null ? "0%" : `${pct}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
