"use client";

import { useEffect, useState } from "react";
import { ChartColumn } from "lucide-react";

import { website } from "@/lib/api";
import { useI18n } from "../../app/providers/I18nProvider";
import { Card } from "@/components/ui/kit";

/**
 * The shop owner's own traffic: 30 days of visits to their published
 * /s/<slug>/ page. Hidden entirely until at least one visit exists, so a
 * fresh unpublished site is not greeted by a wall of zeros.
 */
export default function VisitsCard() {
  const { t } = useI18n();
  const [data, setData] = useState(null);

  useEffect(() => {
    website.visits().then((response) => setData(response.data)).catch(() => {});
  }, []);

  if (!data || !data.visits) return null;
  const values = data.series.map((point) => point.visits);
  const max = Math.max(...values, 1);
  const step = 100 / Math.max(values.length - 1, 1);
  const path = values
    .map((v, i) => `${i ? "L" : "M"}${(i * step).toFixed(1)},${(34 - (v / max) * 30).toFixed(1)}`)
    .join(" ");

  return (
    <Card className="mb-6 p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="flex items-center gap-2 font-display font-semibold">
            <ChartColumn size={17} className="text-accent" />{t("website.visitsTitle")}
          </h2>
          <p className="mt-1 text-sm text-muted">{t("website.visitsHint")}</p>
        </div>
        <div className="text-end">
          <div className="text-2xl font-bold tabular-nums">{data.visits}</div>
          <div className="text-xs text-muted">
            {t("website.visitsVisitors", { count: data.visitors })}
          </div>
          {typeof data.orders === "number" && (
            <div className="mt-1 text-xs text-muted">
              {t("website.visitsOrders", { orders: data.orders, confirmed: data.orders_confirmed, rate: data.order_rate })}
            </div>
          )}
        </div>
      </div>
      <svg viewBox="0 0 100 36" className="mt-3 h-12 w-full text-accent" preserveAspectRatio="none" aria-hidden dir="ltr">
        <path d={`${path} L100,34 L0,34 Z`} fill="currentColor" opacity="0.12" stroke="none" />
        <path d={path} fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
      </svg>
    </Card>
  );
}
