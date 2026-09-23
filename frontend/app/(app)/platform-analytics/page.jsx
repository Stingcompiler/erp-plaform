"use client";

import { useEffect, useMemo, useState } from "react";
import { Bot, ChartColumn, Filter, Globe, MonitorSmartphone, MousePointerClick, TrendingDown, TrendingUp, UsersRound } from "lucide-react";

import { platformAnalytics } from "@/lib/api";
import { useAuth } from "../../providers/AuthProvider";
import { useI18n } from "../../providers/I18nProvider";
import { Badge, Card, PageHeader } from "@/components/ui/kit";

const WINDOWS = [7, 30, 90];

/** Percentage change badge against the previous window; null when there is
 * nothing to compare against yet. */
function delta(current, previous) {
  if (!previous) return null;
  return Math.round(((current - previous) / previous) * 100);
}

function DeltaBadge({ value }) {
  const { t } = useI18n();
  if (value === null) return <span className="text-xs text-muted">{t("platformAnalytics.noPrevious")}</span>;
  const up = value >= 0;
  return (
    <span className={`inline-flex items-center gap-1 text-xs font-semibold ${up ? "text-ok" : "text-danger"}`} dir="ltr">
      {up ? <TrendingUp size={13} /> : <TrendingDown size={13} />}
      {up ? "+" : ""}{value}%
    </span>
  );
}

/** Tiny inline sparkline for a KPI card. */
function Sparkline({ points, field }) {
  if (!points?.length) return null;
  const values = points.map((p) => p[field]);
  const max = Math.max(...values, 1);
  const step = 100 / Math.max(values.length - 1, 1);
  const d = values
    .map((v, i) => `${i ? "L" : "M"}${(i * step).toFixed(1)},${(30 - (v / max) * 26).toFixed(1)}`)
    .join(" ");
  return (
    <svg viewBox="0 0 100 32" className="h-8 w-full text-accent/70" preserveAspectRatio="none" aria-hidden dir="ltr">
      <path d={d} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

function KpiCard({ icon: Icon, label, value, deltaValue, spark, sparkField, hint }) {
  return (
    <Card className="p-4 sm:p-5">
      <div className="flex items-center justify-between gap-2">
        <span className="grid h-8 w-8 place-items-center rounded-control bg-accent/10 text-accent"><Icon size={16} /></span>
        {deltaValue !== undefined && <DeltaBadge value={deltaValue} />}
      </div>
      <div className="mt-3 text-2xl font-bold tabular-nums sm:text-3xl">{value}</div>
      <div className="mt-0.5 text-sm text-muted">{label}</div>
      {spark ? <div className="mt-2"><Sparkline points={spark} field={sparkField} /></div> : hint ? <p className="mt-2 text-xs text-muted">{hint}</p> : null}
    </Card>
  );
}

/** The main visits/visitors chart. Hand-rolled SVG: no chart library in the
 * project, and two polylines with a hover ruler do not justify one. */
function TrendChart({ series }) {
  const { t, language } = useI18n();
  const [hover, setHover] = useState(null);
  const W = 720, H = 220, PAD = 8;
  const max = Math.max(...series.map((p) => p.visits), 4);
  const x = (i) => PAD + (i * (W - PAD * 2)) / Math.max(series.length - 1, 1);
  const y = (v) => H - 24 - (v / max) * (H - 48);
  const line = (field) => series.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p[field]).toFixed(1)}`).join(" ");
  const area = `${line("visits")} L${x(series.length - 1).toFixed(1)},${H - 24} L${x(0).toFixed(1)},${H - 24} Z`;
  const fmtDay = (iso) => new Date(`${iso}T00:00:00`).toLocaleDateString(language === "ar" ? "ar" : "en", { day: "numeric", month: "short" });
  const point = hover === null ? null : series[hover];
  return (
    <div dir="ltr">
      <svg
        viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={t("platformAnalytics.trendTitle")}
        onMouseLeave={() => setHover(null)}
        onMouseMove={(event) => {
          const rect = event.currentTarget.getBoundingClientRect();
          const i = Math.round(((event.clientX - rect.left) / rect.width) * (series.length - 1));
          setHover(Math.min(Math.max(i, 0), series.length - 1));
        }}
      >
        {[0.25, 0.5, 0.75, 1].map((f) => (
          <line key={f} x1={PAD} x2={W - PAD} y1={y(max * f)} y2={y(max * f)} className="stroke-line" strokeDasharray="3 5" strokeWidth="1" />
        ))}
        <path d={area} className="fill-accent/10" />
        <path d={line("visits")} className="stroke-accent" fill="none" strokeWidth="2.5" strokeLinecap="round" />
        <path d={line("visitors")} className="stroke-ink/35" fill="none" strokeWidth="1.5" strokeDasharray="4 4" />
        {point && (
          <g>
            <line x1={x(hover)} x2={x(hover)} y1={16} y2={H - 24} className="stroke-ink/25" strokeWidth="1" />
            <circle cx={x(hover)} cy={y(point.visits)} r="4" className="fill-accent" />
            <circle cx={x(hover)} cy={y(point.visitors)} r="3" className="fill-ink/50" />
          </g>
        )}
        <text x={PAD} y={H - 6} className="fill-muted text-[11px]">{fmtDay(series[0].date)}</text>
        <text x={W - PAD} y={H - 6} textAnchor="end" className="fill-muted text-[11px]">{fmtDay(series[series.length - 1].date)}</text>
      </svg>
      <div className="mt-1 flex min-h-6 items-center justify-between text-sm" dir={language === "ar" ? "rtl" : "ltr"}>
        <div className="flex items-center gap-4 text-xs text-muted">
          <span className="inline-flex items-center gap-1.5"><span className="h-0.5 w-4 rounded bg-accent" />{t("platformAnalytics.visits")}</span>
          <span className="inline-flex items-center gap-1.5"><span className="h-0.5 w-4 rounded bg-ink/35" />{t("platformAnalytics.visitors")}</span>
        </div>
        {point && (
          <span className="tabular-nums text-muted">
            {fmtDay(point.date)} · {t("platformAnalytics.visits")} {point.visits} · {t("platformAnalytics.visitors")} {point.visitors}
          </span>
        )}
      </div>
    </div>
  );
}

/** Ranked rows with a proportional bar — top pages and top referrers. */
function RankedList({ rows, labelFor, max }) {
  return (
    <div className="mt-4 space-y-2.5">
      {rows.map((row) => (
        <div key={labelFor(row)} className="grid grid-cols-[1fr_auto] items-center gap-3">
          <div className="min-w-0">
            <div className="truncate text-sm font-medium" dir="ltr">{labelFor(row)}</div>
            <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-paper">
              <div className="h-full rounded-full bg-accent/60" style={{ width: `${(row.visits / max) * 100}%` }} />
            </div>
          </div>
          <div className="tabular-nums text-sm text-muted">{row.visits}</div>
        </div>
      ))}
    </div>
  );
}

function SplitBar({ title, icon: Icon, parts }) {
  const total = parts.reduce((sum, part) => sum + part.value, 0) || 1;
  return (
    <Card className="p-5">
      <h2 className="flex items-center gap-2 font-display text-base font-semibold"><Icon size={16} className="text-accent" />{title}</h2>
      <div className="mt-4 flex h-2.5 overflow-hidden rounded-full bg-paper" dir="ltr">
        {parts.map((part) => (
          <div key={part.label} className={part.cls} style={{ width: `${(part.value / total) * 100}%` }} />
        ))}
      </div>
      <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-sm">
        {parts.map((part) => (
          <span key={part.label} className="inline-flex items-center gap-1.5 text-muted">
            <span className={`h-2 w-2 rounded-full ${part.cls}`} />
            {part.label} <b className="tabular-nums text-ink">{Math.round((part.value / total) * 100)}%</b>
          </span>
        ))}
      </div>
    </Card>
  );
}

export default function PlatformAnalyticsPage() {
  const { user, can } = useAuth();
  const { t } = useI18n();
  const [days, setDays] = useState(30);
  const [data, setData] = useState(null);
  const [funnel, setFunnel] = useState(null);
  const [error, setError] = useState("");

  const allowed = user?.is_platform_admin && can("platform.seo.view");
  useEffect(() => {
    if (!allowed) return;
    platformAnalytics.overview(days)
      .then((response) => setData(response.data))
      .catch(() => setError(t("platformAnalytics.loadError")));
    platformAnalytics.funnel(days)
      .then((response) => setFunnel(response.data.stages))
      .catch(() => {});
  }, [allowed, days, t]);

  const totals = data?.totals;
  const maxPage = useMemo(() => Math.max(...(data?.top_pages || []).map((r) => r.visits), 1), [data]);
  const maxRef = useMemo(() => Math.max(...(data?.top_referrers || []).map((r) => r.visits), 1), [data]);

  if (!allowed) {
    return <Card className="mx-auto mt-16 max-w-md p-8 text-center"><p className="text-muted">{t("shell.noAccessBody", { module: t("nav.platformAnalytics") })}</p></Card>;
  }
  return (
    <div>
      <PageHeader
        title={t("platformAnalytics.title")}
        subtitle={t("platformAnalytics.subtitle")}
        actions={
          <div className="flex rounded-control border border-line bg-surface p-0.5">
            {WINDOWS.map((window) => (
              <button
                key={window} type="button" onClick={() => setDays(window)}
                className={`tap rounded-control px-3 py-1.5 text-sm font-medium transition-colors ${days === window ? "bg-accent text-white" : "text-muted hover:text-ink"}`}
              >
                {t("platformAnalytics.window", { days: window })}
              </button>
            ))}
          </div>
        }
      />
      {error && <p role="alert" className="mb-5 rounded-control bg-danger/10 p-3 text-sm text-danger">{error}</p>}

      <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
        <KpiCard
          icon={MousePointerClick} label={t("platformAnalytics.visits")} value={totals ? totals.visits : "…"}
          deltaValue={totals ? delta(totals.visits, totals.previous_visits) : undefined}
          spark={data?.series} sparkField="visits"
        />
        <KpiCard
          icon={UsersRound} label={t("platformAnalytics.visitors")} value={totals ? totals.visitors : "…"}
          deltaValue={totals ? delta(totals.visitors, totals.previous_visitors) : undefined}
          spark={data?.series} sparkField="visitors"
        />
        <KpiCard
          icon={ChartColumn} label={t("platformAnalytics.pagesPerVisitor")} value={totals ? totals.pages_per_visitor : "…"}
          hint={t("platformAnalytics.pagesPerVisitorHint")}
        />
        <KpiCard
          icon={Bot} label={t("platformAnalytics.botVisits")} value={totals ? totals.bot_visits : "…"}
          hint={t("platformAnalytics.botVisitsHint")}
        />
      </div>

      <Card className="mt-5 p-5">
        <h2 className="font-display text-lg font-semibold">{t("platformAnalytics.trendTitle")}</h2>
        {data?.series?.length ? <div className="mt-3"><TrendChart series={data.series} /></div> : <p className="mt-4 text-sm text-muted">{t("platformAnalytics.empty")}</p>}
      </Card>

      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <Card className="p-5">
          <h2 className="font-display text-lg font-semibold">{t("platformAnalytics.topPages")}</h2>
          {data?.top_pages?.length
            ? <RankedList rows={data.top_pages} labelFor={(row) => row.path} max={maxPage} />
            : <p className="mt-4 text-sm text-muted">{t("platformAnalytics.empty")}</p>}
        </Card>
        <Card className="p-5">
          <h2 className="font-display text-lg font-semibold">{t("platformAnalytics.topReferrers")}</h2>
          <p className="mt-1 text-sm text-muted">{t("platformAnalytics.topReferrersHint")}</p>
          {data?.top_referrers?.length
            ? <RankedList rows={data.top_referrers} labelFor={(row) => row.host === "direct" ? t("platformAnalytics.direct") : row.host} max={maxRef} />
            : <p className="mt-4 text-sm text-muted">{t("platformAnalytics.empty")}</p>}
        </Card>
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <SplitBar
          title={t("platformAnalytics.devices")} icon={MonitorSmartphone}
          parts={[
            { label: t("platformAnalytics.phone"), value: data?.devices?.phone || 0, cls: "bg-accent" },
            { label: t("platformAnalytics.desktop"), value: data?.devices?.desktop || 0, cls: "bg-ink/30" },
          ]}
        />
        <SplitBar
          title={t("platformAnalytics.languages")} icon={Globe}
          parts={[
            { label: "العربية", value: data?.languages?.ar || 0, cls: "bg-accent" },
            { label: "English", value: data?.languages?.en || 0, cls: "bg-ink/30" },
          ]}
        />
      </div>

      {funnel && (
        <Card className="mt-5 p-5">
          <h2 className="flex items-center gap-2 font-display text-lg font-semibold">
            <Filter size={17} className="text-accent" />{t("platformAnalytics.funnelTitle")}
          </h2>
          <p className="mt-1 text-sm text-muted">{t("platformAnalytics.funnelHint")}</p>
          <div className="mt-5 grid gap-2 sm:grid-cols-3 xl:grid-cols-6">
            {funnel.map((stage, index) => {
              const max = funnel[0]?.count || 1;
              return (
                <div key={stage.key} className="rounded-card border border-line bg-paper/60 p-3">
                  <div className="text-xs text-muted">{index + 1}. {t(`platformAnalytics.stage.${stage.key}`)}</div>
                  <div className="mt-1 text-xl font-bold tabular-nums">{stage.count}</div>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-line/60">
                    <div className="h-full rounded-full bg-accent" style={{ width: `${Math.max((stage.count / max) * 100, stage.count ? 2 : 0)}%` }} />
                  </div>
                  <div className="mt-1.5 min-h-4 text-xs tabular-nums text-muted" dir="ltr">
                    {stage.rate !== null && `${stage.rate}% ←`}
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      )}

      {data?.top_company_pages?.length > 0 && (
        <Card className="mt-5 p-5">
          <h2 className="font-display text-lg font-semibold">{t("platformAnalytics.companyPages")}</h2>
          <p className="mt-1 text-sm text-muted">{t("platformAnalytics.companyPagesHint")}</p>
          <div className="mt-3 divide-y divide-line">
            {data.top_company_pages.map((row) => (
              <div key={row.path} className="flex items-center justify-between gap-4 py-2.5">
                <div className="min-w-0">
                  <div className="truncate font-medium">{row.name}</div>
                  <a href={`${row.path}/`} target="_blank" rel="noreferrer" className="text-xs text-accent hover:underline" dir="ltr">{row.path}</a>
                </div>
                <div className="flex items-center gap-2">
                  {row.orders > 0 && <Badge tone="ok">{t("platformAnalytics.ordersFromPages", { n: row.orders })}</Badge>}
                  <Badge tone="accent">{row.visits}</Badge>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
