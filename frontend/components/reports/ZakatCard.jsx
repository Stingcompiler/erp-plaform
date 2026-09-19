"use client";

import { useCallback, useEffect, useState } from "react";
import { Download, Moon } from "lucide-react";

import { API_BASE, reports } from "@/lib/api";
import { useI18n } from "../../app/providers/I18nProvider";
import { Button, Card, Field, Select } from "@/components/ui/kit";

const HIJRI_MONTHS_AR = ["محرم", "صفر", "ربيع الأول", "ربيع الآخر", "جمادى الأولى", "جمادى الآخرة", "رجب", "شعبان", "رمضان", "شوال", "ذو القعدة", "ذو الحجة"];
const HIJRI_MONTHS_EN = ["Muharram", "Safar", "Rabi' I", "Rabi' II", "Jumada I", "Jumada II", "Rajab", "Sha'ban", "Ramadan", "Shawwal", "Dhu al-Qa'dah", "Dhu al-Hijjah"];

/**
 * Zakat on trade goods for the hawl day: stock at selling (or cost) value,
 * cash in the tills, bank balances and collectible receivables, less
 * payables, at 2.5% per lunar year. The Hijri date is the tabular calendar
 * (within a day of the sighted one); the owner picks the hawl month/day
 * and the card says when it next falls.
 */
export default function ZakatCard() {
  const { t, language } = useI18n();
  const [valuation, setValuation] = useState("sale");
  const [excludeDoubtful, setExcludeDoubtful] = useState(false);
  const [hawl, setHawl] = useState(() => {
    try { return JSON.parse(localStorage.getItem("zakat.hawl") || "null") || { month: "", day: "" }; } catch { return { month: "", day: "" }; }
  });
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);

  const params = {
    valuation,
    ...(excludeDoubtful ? { exclude_doubtful: 1 } : {}),
    ...(hawl.month && hawl.day ? { hawl_month: hawl.month, hawl_day: hawl.day } : {}),
  };
  const load = useCallback(() => {
    reports.zakat(params).then((r) => { setData(r.data); setError(false); }).catch(() => setError(true));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [valuation, excludeDoubtful, hawl.month, hawl.day]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    try { localStorage.setItem("zakat.hawl", JSON.stringify(hawl)); } catch { /* per-viewer convenience only */ }
  }, [hawl]);

  const money = (v) => Number(v ?? 0).toLocaleString(language === "ar" ? "ar" : "en", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const months = language === "ar" ? HIJRI_MONTHS_AR : HIJRI_MONTHS_EN;
  const csvUrl = `${API_BASE}/reports/zakat/?${new URLSearchParams({ ...params, format: "csv" })}`;

  const lines = data ? [
    [t("reports.zakatStock", { basis: t(valuation === "sale" ? "reports.zakatAtSale" : "reports.zakatAtCost") }), data.stock, "+"],
    [t("reports.zakatCash"), data.cash_in_tills, "+"],
    [t("reports.zakatBank"), data.bank, "+"],
    [t("reports.zakatReceivables"), data.counted_receivables, "+"],
    [t("reports.zakatPayables"), data.payables, "−"],
  ] : [];

  return (
    <Card className="p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 font-display text-sm font-semibold uppercase tracking-wide text-muted">
            <Moon size={15} /> {t("reports.zakatTitle")}
          </h2>
          {data && (
            <p className="mt-1 text-sm text-ink">
              {t("reports.zakatToday")} <span className="font-semibold">{language === "ar" ? data.hijri_ar : data.hijri_en}</span>
              <span className="text-muted"> · {data.as_of}</span>
            </p>
          )}
        </div>
        <a href={csvUrl}><Button variant="ghost"><Download size={15} /> CSV</Button></a>
      </div>

      <div className="mb-4 grid gap-3 sm:grid-cols-4">
        <Field label={t("reports.zakatValuation")}>
          <Select value={valuation} onChange={(e) => setValuation(e.target.value)}>
            <option value="sale">{t("reports.zakatAtSale")}</option>
            <option value="cost">{t("reports.zakatAtCost")}</option>
          </Select>
        </Field>
        <Field label={t("reports.zakatHawlMonth")}>
          <Select value={hawl.month} onChange={(e) => setHawl((h) => ({ ...h, month: e.target.value }))}>
            <option value="">—</option>
            {months.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
          </Select>
        </Field>
        <Field label={t("reports.zakatHawlDay")}>
          <Select value={hawl.day} onChange={(e) => setHawl((h) => ({ ...h, day: e.target.value }))}>
            <option value="">—</option>
            {Array.from({ length: 30 }, (_, i) => <option key={i + 1} value={i + 1}>{i + 1}</option>)}
          </Select>
        </Field>
        <label className="flex items-end gap-2 pb-2 text-sm text-ink">
          <input type="checkbox" checked={excludeDoubtful} onChange={(e) => setExcludeDoubtful(e.target.checked)} />
          {t("reports.zakatExcludeDoubtful")}
        </label>
      </div>

      {error && <p className="text-sm text-danger">{t("common.loadError")}</p>}
      {data && (
        <>
          {data.next_hawl && (
            <p className="mb-3 text-sm text-muted">{t("reports.zakatNextHawl", { date: data.next_hawl })}</p>
          )}
          <div className="divide-y divide-line rounded-card border border-line text-sm">
            {lines.map(([label, value, sign]) => (
              <div key={label} className="flex items-center justify-between px-3 py-2">
                <span>{label}</span>
                <span className="tabular" dir="ltr">{sign} {money(value)}</span>
              </div>
            ))}
            <div className="flex items-center justify-between bg-paper px-3 py-2 font-semibold">
              <span>{t("reports.zakatBase")}</span>
              <span className="tabular" dir="ltr">{money(data.base)}</span>
            </div>
            <div className="flex items-center justify-between px-3 py-3 text-base font-semibold text-accent">
              <span>{t("reports.zakatDue")}</span>
              <span className="tabular" dir="ltr">{money(data.zakat)}</span>
            </div>
          </div>
          <p className="mt-3 text-xs text-muted">
            {t("reports.zakatNote", {
              items: data.stock_items,
              other: money(valuation === "sale" ? data.stock_at_cost : data.stock_at_sale),
              doubtful: money(data.doubtful_receivables),
            })}
          </p>
        </>
      )}
    </Card>
  );
}
