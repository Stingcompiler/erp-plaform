"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Banknote, Download, Lock, TrendingUp } from "lucide-react";

import { useAuth } from "../../providers/AuthProvider";
import { useI18n } from "../../providers/I18nProvider";
import { platformFinance as api } from "@/lib/api";
import { Badge, Button, Card, PageHeader } from "@/components/ui/kit";

const STATUS_TONE = { active: "ok", trialing: "accent", grace: "warn", read_only: "warn", suspended: "danger", cancelled: "muted", legacy: "muted" };

// Western digits in both languages, like every other money figure in the app.
function fmtMoney(value, currency) {
  const n = Number(value || 0);
  return `${n.toLocaleString("en", { maximumFractionDigits: 2 })} ${currency}`;
}

function fmtMonth(key, language) {
  const [y, m] = key.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleDateString(language === "ar" ? "ar" : "en", { month: "short", year: "2-digit" });
}

/** Invoiced vs collected per month. Two bars per month, hand-drawn SVG —
 * the analytics page set the precedent of no chart library. */
function MonthlyBars({ rows, currency }) {
  const { t, language } = useI18n();
  const [hover, setHover] = useState(null);
  const W = 720, H = 200, PAD = 8, LBL = 22;
  const max = Math.max(...rows.flatMap((r) => [Number(r.invoiced), Number(r.collected)]), 1);
  const slot = (W - PAD * 2) / rows.length;
  const bw = Math.max(4, Math.min(22, slot * 0.32));
  const y = (v) => H - LBL - (v / max) * (H - LBL - 12);
  const point = hover === null ? null : rows[hover];
  return (
    <div dir="ltr">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={t("platformFinance.monthlyTitle")} onMouseLeave={() => setHover(null)}>
        {[0.5, 1].map((f) => <line key={f} x1={PAD} x2={W - PAD} y1={y(max * f)} y2={y(max * f)} className="stroke-line" strokeDasharray="3 5" strokeWidth="1" />)}
        {rows.map((r, i) => {
          const cx = PAD + slot * i + slot / 2;
          return (
            <g key={r.month} onMouseEnter={() => setHover(i)}>
              <rect x={cx - bw - 1} y={y(Number(r.invoiced))} width={bw} height={H - LBL - y(Number(r.invoiced))} className="fill-ink/25" rx="2" />
              <rect x={cx + 1} y={y(Number(r.collected))} width={bw} height={H - LBL - y(Number(r.collected))} className="fill-accent" rx="2" />
              <rect x={cx - slot / 2} y={0} width={slot} height={H} fill="transparent" />
              {(rows.length <= 12 || i % 3 === 0) && <text x={cx} y={H - 6} textAnchor="middle" className="fill-muted text-[10px]">{fmtMonth(r.month, language)}</text>}
            </g>
          );
        })}
      </svg>
      <div className="mt-1 flex min-h-6 flex-wrap items-center justify-between gap-2 text-xs text-muted" dir={language === "ar" ? "rtl" : "ltr"}>
        <div className="flex items-center gap-4">
          <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-ink/25" />{t("platformFinance.invoiced")}</span>
          <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-accent" />{t("platformFinance.collected")}</span>
        </div>
        {point && <span className="tabular">{fmtMonth(point.month, language)} · {t("platformFinance.invoiced")} {fmtMoney(point.invoiced, currency)} · {t("platformFinance.collected")} {fmtMoney(point.collected, currency)}</span>}
      </div>
    </div>
  );
}

function Kpi({ label, value, hint, tone }) {
  return (
    <Card className="p-4">
      <div className="text-xs text-muted">{label}</div>
      <div className={`mt-1 font-display text-xl font-semibold tabular ${tone === "danger" ? "text-danger" : ""}`}>{value}</div>
      {hint && <div className="mt-0.5 text-xs text-muted">{hint}</div>}
    </Card>
  );
}

export default function PlatformFinancePage() {
  const { can } = useAuth();
  const { t, language } = useI18n();
  const canView = can("platform.billing.view");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [months, setMonths] = useState(12);
  const [currency, setCurrency] = useState(null);

  const load = useCallback(async () => {
    try { const res = await api.report(months); setData(res.data); setError(""); }
    catch { setError(t("platformFinance.loadError")); }
  }, [months, t]);
  useEffect(() => { if (canView) load(); }, [canView, load]);

  const block = useMemo(() => {
    const list = data?.currencies || [];
    return list.find((c) => c.currency === currency) || list[0] || null;
  }, [data, currency]);

  const fmt = (v) => v ? new Date(v).toLocaleDateString(language === "ar" ? "ar" : "en") : "—";
  const companies = useMemo(() => (data?.companies || []).filter((c) => !block || c.currency === block.currency), [data, block]);

  if (!canView) return <Card className="mx-auto mt-16 max-w-md p-8 text-center"><Lock className="mx-auto text-muted" /><p className="mt-3 text-muted">{t("platformFinance.noAccess")}</p></Card>;

  const conv = data?.trial_conversion;
  return (
    <div>
      <PageHeader
        title={t("platformFinance.title")} subtitle={t("platformFinance.subtitle")}
        actions={<a href={api.csvUrl()} className="tap inline-flex min-h-10 items-center gap-2 rounded-control border border-line bg-surface px-4 py-2 text-sm font-semibold"><Download size={16} />{t("platformFinance.exportCsv")}</a>}
      />
      {error && <div role="alert" className="mb-4 rounded-control bg-danger/10 p-3 text-sm text-danger">{error}</div>}
      {data && !data.currencies.length && <Card className="p-10 text-center text-muted">{t("platformFinance.empty")}</Card>}
      {block && (
        <>
          <div className="mb-4 flex flex-wrap items-center gap-2">
            {data.currencies.length > 1 && data.currencies.map((c) => (
              <Button key={c.currency} variant={c.currency === block.currency ? "primary" : "outline"} onClick={() => setCurrency(c.currency)}>{c.currency}</Button>
            ))}
            <span className="ms-auto text-xs text-muted">{t("platformFinance.currencyNote")}</span>
            <div className="flex gap-1">
              {[6, 12, 24].map((m) => <Button key={m} variant={m === months ? "primary" : "ghost"} onClick={() => setMonths(m)}>{t("platformFinance.monthsN", { n: m })}</Button>)}
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Kpi label={t("platformFinance.mrr")} value={fmtMoney(block.mrr, block.currency)} hint={t("platformFinance.mrrHint")} />
            <Kpi label={t("platformFinance.arr")} value={fmtMoney(block.arr, block.currency)} />
            <Kpi label={t("platformFinance.collectedMonth")} value={fmtMoney(block.collected_month, block.currency)} hint={t("platformFinance.collectedWindow", { n: months, amount: fmtMoney(block.collected_window, block.currency) })} />
            <Kpi label={t("platformFinance.outstanding")} value={fmtMoney(block.outstanding, block.currency)} hint={t("platformFinance.overdue", { amount: fmtMoney(block.overdue, block.currency) })} tone={Number(block.overdue) > 0 ? "danger" : undefined} />
          </div>
          <div className="mt-3 grid gap-3 sm:grid-cols-3">
            <Kpi label={t("platformFinance.statusMix")} value={Object.entries(data.statuses).map(([k, v]) => `${v} ${t(`platformCompanies.status.${k}`)}`).join(" · ") || "—"} />
            <Kpi label={t("platformFinance.trialConversion")} value={conv?.rate == null ? "—" : `${Math.round(conv.rate * 100)}%`} hint={t("platformFinance.trialConversionHint", { converted: conv?.converted ?? 0, total: conv?.ever_trialing ?? 0 })} />
            <Kpi label={t("platformFinance.subsMovement")} value={`+${data.monthly_subscriptions.reduce((n, r) => n + r.new, 0)} / −${data.monthly_subscriptions.reduce((n, r) => n + r.cancelled, 0)}`} hint={t("platformFinance.subsMovementHint", { n: months })} />
          </div>

          <Card className="mt-5 p-5">
            <h2 className="mb-3 flex items-center gap-2 font-display font-semibold"><TrendingUp size={18} className="text-accent" />{t("platformFinance.monthlyTitle")}</h2>
            <MonthlyBars rows={block.monthly} currency={block.currency} />
          </Card>

          <Card className="mt-5 overflow-x-auto">
            <div className="flex items-center gap-2 px-5 pt-5 font-display font-semibold"><Banknote size={18} className="text-accent" />{t("platformFinance.byPlan")}</div>
            <table className="stack-sm mt-3 w-full sm:min-w-[640px] text-sm">
              <thead className="bg-paper text-xs uppercase tracking-wide text-muted">
                <tr><th className="px-4 py-2 text-start">{t("platformFinance.plan")}</th><th className="px-3 py-2 text-center">{t("platformCompanies.status.active")}</th><th className="px-3 py-2 text-center">{t("platformCompanies.status.trialing")}</th><th className="px-3 py-2 text-center">{t("platformFinance.otherStates")}</th><th className="px-3 py-2 text-end">{t("platformFinance.mrr")}</th><th className="px-3 py-2 text-end">{t("platformFinance.collectedN", { n: months })}</th><th className="px-3 py-2 text-end">{t("platformFinance.outstanding")}</th></tr>
              </thead>
              <tbody className="divide-y divide-line">
                {block.by_plan.map((p) => (
                  <tr key={p.code}><td className="px-4 py-2 font-medium">{p.name}</td><td className="px-3 py-2 text-center tabular">{p.active}</td><td className="px-3 py-2 text-center tabular">{p.trialing}</td><td className="px-3 py-2 text-center tabular text-muted">{p.other}</td><td className="px-3 py-2 text-end tabular">{fmtMoney(p.mrr, block.currency)}</td><td className="px-3 py-2 text-end tabular">{fmtMoney(p.collected_window, block.currency)}</td><td className={`px-3 py-2 text-end tabular ${Number(p.outstanding) > 0 ? "text-warn" : ""}`}>{fmtMoney(p.outstanding, block.currency)}</td></tr>
                ))}
              </tbody>
            </table>
          </Card>

          <Card className="mt-5 overflow-x-auto">
            <div className="px-5 pt-5 font-display font-semibold">{t("platformFinance.byCompany")}</div>
            <table className="stack-sm mt-3 w-full sm:min-w-[720px] text-sm">
              <thead className="bg-paper text-xs uppercase tracking-wide text-muted">
                <tr><th className="px-4 py-2 text-start">{t("platformCompanies.company")}</th><th className="px-3 py-2 text-start">{t("platformFinance.plan")}</th><th className="px-3 py-2 text-end">{t("platformFinance.monthlyPrice")}</th><th className="px-3 py-2 text-end">{t("platformFinance.outstanding")}</th><th className="px-3 py-2 text-start">{t("platformFinance.lastPayment")}</th><th className="px-3 py-2 text-start">{t("platformFinance.renewal")}</th></tr>
              </thead>
              <tbody className="divide-y divide-line">
                {companies.map((c) => (
                  <tr key={c.company_id}><td className="px-4 py-2 font-medium">{c.company}</td><td className="px-3 py-2">{c.plan} <Badge tone={STATUS_TONE[c.status] || "muted"}>{t(`platformCompanies.status.${c.status}`)}</Badge></td><td className="px-3 py-2 text-end tabular">{c.monthly_price ? fmtMoney(c.monthly_price, c.currency) : "—"}</td><td className={`px-3 py-2 text-end tabular ${Number(c.outstanding) > 0 ? "text-warn font-semibold" : ""}`}>{fmtMoney(c.outstanding, c.currency)}</td><td className="px-3 py-2 text-muted">{fmt(c.last_payment_at)}</td><td className="px-3 py-2 text-muted">{fmt(c.status === "trialing" ? c.trial_ends_at : c.period_ends_at)}</td></tr>
                ))}
              </tbody>
            </table>
          </Card>
        </>
      )}
    </div>
  );
}
