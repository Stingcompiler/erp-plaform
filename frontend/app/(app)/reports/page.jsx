"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { BarChart3, Download, Lock } from "lucide-react";

import { API_BASE, reports } from "@/lib/api";
import { useAuth } from "../../providers/AuthProvider";
import { useI18n } from "../../providers/I18nProvider";
import { Badge, Button, Card, Field, Input, PageHeader, Select } from "@/components/ui/kit";
import BarList from "@/components/reports/BarList";
import ZakatCard from "@/components/reports/ZakatCard";
import OperationalReports from "@/components/reports/OperationalReports";
import ReportState, { ReportFailed } from "@/components/reports/ReportState";
import TabBar from "@/components/ui/TabBar";
import { EmptyState } from "@/components/ui/EmptyState";
import { useHashTab } from "@/lib/useHashTab";
import { expenseCategory } from "@/lib/expenseCategories";
import { localToday } from "@/lib/dates";
import { formatAmount } from "@/lib/money";
import { useMoney } from "@/lib/useMoney";
import { LOADING, planIncludes, slotFromError } from "@/lib/reportSlots";
import { SkeletonLines } from "@/components/ui/Skeleton";

// The page opens on this month, not all time: every report over the whole
// history on each visit was the slowest screen in the app, and "this month"
// is what the owner asks first. "All time" is one click away.
function thisMonth() {
  const today = localToday();
  return { start: `${today.slice(0, 8)}01`, end: today };
}

// A headline figure. `slot` is the request it comes from: while it loads
// the tile keeps its shape, and a failed request says so on the tile itself
// (with its own retry) instead of showing a dash that reads like "nothing".
function Kpi({ label, value, tone = "ink", slot, onRetry }) {
  const toneClass = tone === "accent" ? "text-accent" : tone === "ok" ? "text-ok" : "text-ink";
  const status = slot?.status || "ok";
  return (
    <Card className="p-5">
      <div className="text-sm text-muted">{label}</div>
      {status === "loading" ? (
        <SkeletonLines lines={1} className="mt-2" />
      ) : status !== "ok" ? (
        <div className="mt-2"><ReportFailed status={status} onRetry={onRetry} compact /></div>
      ) : (
        <div className={`tabular mt-2 break-words text-2xl font-medium ${toneClass}`}>{value}</div>
      )}
    </Card>
  );
}

function SectionCard({ title, action, children }) {
  return (
    <Card className="p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-display text-sm font-semibold uppercase tracking-wide text-muted">
          {title}
        </h2>
        {action}
      </div>
      {children}
    </Card>
  );
}

function CsvLink({ href }) {
  return (
    <a href={href}>
      <Button variant="ghost">
        <Download size={15} /> CSV
      </Button>
    </a>
  );
}

export default function ReportsPage() {
  const { canRead, user } = useAuth();
  const { t, language } = useI18n();
  const { money: withCurrency } = useMoney();
  const reportAreas = user?.report_areas || [];
  const salesReports = reportAreas.includes("sales");
  const inventoryReports = reportAreas.includes("inventory");
  const purchasingReports = reportAreas.includes("purchasing");
  const financeReports = reportAreas.includes("finance");
  const hrReports = reportAreas.includes("hr");
  const payrollReports = hrReports || financeReports;
  // One tab per report area the role can read; the date range above them
  // applies to every tab. Payroll sits with HR, or with finance for a CFO
  // who has no HR area.
  const reportTabs = [
    ...(salesReports || inventoryReports || financeReports ? [{ id: "overview", label: t("reports.tabOverview") }] : []),
    ...(salesReports ? [{ id: "sales", label: t("reports.tabSales") }] : []),
    ...(purchasingReports ? [{ id: "purchasing", label: t("reports.tabPurchasing") }] : []),
    ...(financeReports ? [{ id: "finance", label: t("reports.tabFinance") }] : []),
    ...(hrReports ? [{ id: "hr", label: t("reports.tabHr") }] : []),
  ];
  const payrollTab = hrReports ? "hr" : "finance";
  const [tab, setTab] = useHashTab(reportTabs.map((x) => x.id));
  // Headline figures carry the currency; a figure that is not there shows a
  // dash, never 0.00 — a failed profit report used to read as "profit 0.00".
  const money = (v) => withCurrency(v, { empty: "—" });
  // Table cells sit under a header: the figure alone, two decimals.
  const cell = (v) => formatAmount(v, { empty: "—" });
  // Ratios are null when undefined (zero denominator) — show a dash rather
  // than 0%, which would read as a real measurement.
  const pct = (v) =>
    v === null || v === undefined
      ? t("reports.undefinedRatio")
      : `${Number(v).toLocaleString("en-US", { maximumFractionDigits: 1 })}%`;
  const [range, setRange] = useState(thisMonth);
  const [costMethod, setCostMethod] = useState("standard");
  const [forecastWeeks, setForecastWeeks] = useState(8);
  // Every report's own state: { status, data } per key (lib/reportSlots).
  const [slots, setSlots] = useState({});
  const generation = useRef(0);

  // The requests the open tab needs, by key. Only the open tab's reports:
  // every area at once was a dozen heavy queries for figures the reader
  // could not see.
  const requestsFor = useCallback(() => {
    const p = {};
    if (range.start) p.start = range.start;
    if (range.end) p.end = range.end;
    const overview = tab === "overview";
    const list = {};
    if (overview && salesReports) {
      list.summary = () => reports.salesSummary(p);
      list.byProduct = () => reports.salesByProduct(p);
    }
    if (tab === "sales" && salesReports) {
      list.aging = () => reports.arAging();
      list.collections = () => reports.receivablesDue();
    }
    if (overview && inventoryReports) {
      // Stock held at the end of the range, not always today's.
      list.valuation = () => reports.inventoryValuation({
        method: costMethod, ...(range.end ? { as_of: range.end } : {}),
      });
    }
    if (tab === "purchasing" && purchasingReports) {
      list.payables = () => reports.payablesDue();
      list.apAging = () => reports.apAging();
      list.purchases = () => reports.purchasesSummary(p);
    }
    if ((overview || tab === "finance") && financeReports) {
      list.income = () => reports.incomeStatement({ ...p, method: costMethod });
    }
    if (tab === "finance" && financeReports) {
      list.cash = () => reports.cashFlow(p);
      list.forecast = () => reports.cashFlowForecast({ weeks: forecastWeeks });
      list.kpis = () => reports.cfoKpis({ ...p, method: costMethod });
    }
    if (tab === "hr" && hrReports) list.hrSummary = () => reports.hrSummary(p);
    if (tab === payrollTab && payrollReports) list.payroll = () => reports.payroll(p);
    return list;
  }, [tab, payrollTab, range.start, range.end, costMethod, salesReports, inventoryReports, purchasingReports, financeReports, hrReports, payrollReports, forecastWeeks]);

  const run = useCallback((key, fetcher, id) => {
    setSlots((current) => ({ ...current, [key]: LOADING }));
    return fetcher()
      .then((r) => ({ status: "ok", data: r.data }))
      .catch((err) => ({ status: slotFromError(err), data: null }))
      .then((slot) => {
        // A newer range or tab replaced this request: drop its answer.
        if (id === generation.current) setSlots((current) => ({ ...current, [key]: slot }));
      });
  }, []);

  const load = useCallback(() => {
    const id = ++generation.current;
    Object.entries(requestsFor()).forEach(([key, fetcher]) => run(key, fetcher, id));
  }, [requestsFor, run]);

  // Retry one card: only its own request runs again.
  const retry = (key) => {
    const fetcher = requestsFor()[key];
    if (fetcher) run(key, fetcher, generation.current);
  };

  useEffect(() => {
    load();
  }, [load]);

  if (!canRead("reports")) {
    return (
      <div className="mx-auto mt-16 max-w-md rounded-card border border-line bg-surface p-8 text-center">
        <Lock className="mx-auto text-muted" />
        <h1 className="mt-3 font-display text-xl font-semibold">{t("shell.noAccessTitle")}</h1>
        <p className="mt-1 text-muted">{t("reports.noAccess")}</p>
      </div>
    );
  }

  // A plan without the reports module: the server refuses every report, so
  // say that once instead of four "failed" cards.
  if (!planIncludes(user?.entitlements, "reports")) {
    const owner = user?.role_name === "Business Owner";
    return (
      <div>
        <PageHeader title={t("reports.title")} />
        <Card>
          <EmptyState
            icon={BarChart3}
            title={t("states.reportsNotInPlanTitle")}
            body={t(owner ? "states.reportsNotInPlanOwner" : "states.reportsNotInPlanStaff")}
            action={owner && (
              <Link href="/subscription">
                <Button variant="outline">{t("states.openSubscription")}</Button>
              </Link>
            )}
          />
        </Card>
      </div>
    );
  }

  const slot = (key) => slots[key] || LOADING;
  const data = (key) => (slots[key]?.status === "ok" ? slots[key].data : null);
  const summary = data("summary");
  const income = data("income");
  const valuation = data("valuation");

  const params = {};
  if (range.start) params.start = range.start;
  if (range.end) params.end = range.end;
  const csv = (path, extra = {}) => {
    const qs = new URLSearchParams({ ...params, ...extra, format: "csv" }).toString();
    return `${API_BASE}${path}?${qs}`;
  };

  // The valuation is the stock held at the end of the range when one is set.
  const valuationAsOf = (label) =>
    valuation?.as_of ? `${label} · ${t("reports.valuationAsOf", { date: valuation.as_of })}` : label;
  const methodName = (method) => ({
    standard: t("reports.standardCost"),
    average: t("reports.weightedAverage"),
    fifo: t("reports.fifo"),
  }[method] || method);

  const agingTable = (rows, partyKey, partyLabel) => (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line text-xs uppercase tracking-wide text-muted">
            <th className="px-3 py-2 text-start font-medium">{partyLabel}</th>
            <th className="px-3 py-2 text-end font-medium">{t("reports.current")}</th>
            <th className="px-3 py-2 text-end font-medium">1–30</th>
            <th className="px-3 py-2 text-end font-medium">31–60</th>
            <th className="px-3 py-2 text-end font-medium">61–90</th>
            <th className="px-3 py-2 text-end font-medium">{t("reports.over90")}</th>
            <th className="px-3 py-2 text-end font-medium">{t("common.total")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row[partyKey]} className="border-b border-line last:border-0">
              <td className="px-3 py-2 text-ink">{row.name}</td>
              <td className="tabular px-3 py-2 text-end text-muted">{cell(row.current)}</td>
              <td className="tabular px-3 py-2 text-end text-muted">{cell(row["1_30"])}</td>
              <td className="tabular px-3 py-2 text-end text-muted">{cell(row["31_60"])}</td>
              <td className="tabular px-3 py-2 text-end text-muted">{cell(row["61_90"])}</td>
              <td className="tabular px-3 py-2 text-end text-warn">{cell(row.over_90)}</td>
              <td className="tabular px-3 py-2 text-end font-medium text-ink">{cell(row.total)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  const dueTable = (rows, { key, number, party, partyLabel }) => (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line text-xs uppercase tracking-wide text-muted">
            <th className="px-3 py-2 text-start font-medium">{t("reports.invoiceNo")}</th>
            <th className="px-3 py-2 text-start font-medium">{partyLabel}</th>
            <th className="px-3 py-2 text-start font-medium">{t("reports.dueDate")}</th>
            <th className="px-3 py-2 text-end font-medium">{t("reports.daysOverdue")}</th>
            <th className="px-3 py-2 text-end font-medium">{t("reports.amountDue")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r[key]} className="border-b border-line last:border-0">
              <td className="tabular px-3 py-2 text-ink">{r[number]}</td>
              <td className="px-3 py-2 text-muted">{r[party]}</td>
              <td className="tabular px-3 py-2 text-muted">{r.due_date || "—"}</td>
              <td className="px-3 py-2 text-end">
                {r.days_overdue > 0 ? (
                  <Badge tone="danger">{r.days_overdue}</Badge>
                ) : (
                  <Badge tone="muted">{t("reports.dueSoon")}</Badge>
                )}
              </td>
              <td className="tabular px-3 py-2 text-end font-medium text-ink">{cell(r.amount_due)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  return (
    <div>
      <PageHeader title={t("reports.title")} subtitle={t("reports.subtitleLive")} />

      <Card className="mb-6 p-4">
        <div className="flex flex-wrap items-end gap-3">
          <Field label={t("reports.from")}>
            <Input
              type="date"
              value={range.start}
              onChange={(e) => setRange((r) => ({ ...r, start: e.target.value }))}
            />
          </Field>
          <Field label={t("reports.to")}>
            <Input
              type="date"
              value={range.end}
              onChange={(e) => setRange((r) => ({ ...r, end: e.target.value }))}
            />
          </Field>
          <Button variant="outline" onClick={() => setRange(thisMonth())}>
            {t("reports.thisMonth")}
          </Button>
          <Button variant="outline" onClick={() => setRange({ start: "", end: "" })}>
            {t("reports.allTime")}
          </Button>
          {(inventoryReports || financeReports) && <div className="ms-auto">
            <Field label={t("reports.costingMethod")}>
              <Select value={costMethod} onChange={(e) => setCostMethod(e.target.value)}>
                <option value="standard">{t("reports.standardCost")}</option>
                {/* Average/FIFO are computed company-wide only; a branch
                    reader asking for them got a failed report. */}
                {user?.role_scope !== "branch" && <option value="average">{t("reports.weightedAverage")}</option>}
                {user?.role_scope !== "branch" && <option value="fifo">{t("reports.fifo")}</option>}
              </Select>
            </Field>
          </div>}
        </div>
      </Card>

      {reportTabs.length > 1 && <TabBar value={tab} onChange={setTab} tabs={reportTabs} />}

      {reportTabs.length === 0 && (
        <Card>
          <EmptyState icon={BarChart3} title={t("states.noReportAreasTitle")} body={t("states.noReportAreasBody")} />
        </Card>
      )}

      <div className="space-y-6">
        {tab === "hr" && hrReports && (
          <ReportState slot={slot("hrSummary")} onRetry={() => retry("hrSummary")} isEmpty={() => false} lines={4}>
            {(hrSummary) => (
              <>
                <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                  <Kpi label={t("reports.hrEmployees")} value={hrSummary.employee_total} />
                  <Kpi label={t("reports.hrActive")} tone="ok" value={hrSummary.employees.active || 0} />
                  <Kpi label={t("reports.hrPendingLeave")} value={hrSummary.leave.pending || 0} />
                  <Kpi label={t("reports.hrAbsent")} value={hrSummary.attendance.absent || 0} />
                </div>
                <div className="grid gap-6 lg:grid-cols-2">
                  <SectionCard title={t("reports.hrAttendance")}>
                    <div className="grid gap-4 sm:grid-cols-2">
                      <Kpi label={t("reports.hrPresent")} tone="ok" value={hrSummary.attendance.present || 0} />
                      <Kpi label={t("reports.hrAbsent")} value={hrSummary.attendance.absent || 0} />
                      <Kpi label={t("reports.hrOnLeave")} value={hrSummary.attendance.leave || 0} />
                      <Kpi label={t("reports.hrHalfDay")} value={hrSummary.attendance.half_day || 0} />
                    </div>
                  </SectionCard>
                  <SectionCard title={t("reports.hrFinancialActions")}>
                    <div className="grid gap-4 sm:grid-cols-2">
                      <Kpi label={t("reports.hrPendingAdvances")} value={hrSummary.advances.pending || 0} />
                      <Kpi label={t("reports.hrApprovedAdvances")} value={money(hrSummary.advances.approved_total)} />
                      <Kpi label={t("reports.hrDeductionsCount")} value={hrSummary.deductions.count || 0} />
                      <Kpi label={t("reports.hrDeductionsTotal")} value={money(hrSummary.deductions.total)} />
                    </div>
                  </SectionCard>
                </div>
                <SectionCard title={t("reports.hrByDepartment")}>
                  <BarList
                    items={hrSummary.departments.map((row) => ({ label: row.name, value: row.count }))}
                    format={(v) => String(v)}
                  />
                </SectionCard>
              </>
            )}
          </ReportState>
        )}

        {tab === payrollTab && payrollReports && (
          <SectionCard title={t("reports.payrollTitle")} action={<CsvLink href={csv("/reports/payroll/")} />}>
            <ReportState slot={slot("payroll")} onRetry={() => retry("payroll")} emptyText={t("reports.noPayroll")}>
              {(payroll) => (
                <div className="space-y-4">
                  {payroll.map((run) => (
                    <div key={run.id} className="rounded-control border border-line p-4">
                      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                        <div className="font-medium text-ink">{t("reports.payrollFor", { period: run.period.slice(0, 7) })}</div>
                        <Badge tone={run.status === "approved" ? "ok" : "warn"}>{run.status === "approved" ? t("hr.approved") : t("hr.pending")}</Badge>
                      </div>
                      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                        <Kpi label={t("reports.payrollEmployees")} value={run.employee_count} />
                        <Kpi label={t("reports.payrollBase")} value={money(run.base_total)} />
                        <Kpi label={t("reports.payrollDeductions")} value={money(run.deductions_total)} />
                        <Kpi label={t("reports.payrollNet")} tone="ok" value={money(run.net_total)} />
                      </div>
                      <div className="mt-3 divide-y divide-line text-sm">
                        {run.entries.map((entry) => (
                          <div key={`${run.id}-${entry.employee_name}`} className="flex flex-wrap items-center justify-between gap-2 py-2">
                            <span className="text-ink">{entry.employee_name} <span className="text-muted">· {entry.department_name || "—"} · {entry.position_title || "—"}</span></span>
                            <span className="tabular font-medium">{cell(entry.net_salary)}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </ReportState>
          </SectionCard>
        )}

        {/* Headline KPIs — each tile shows its own report's state. */}
        {tab === "overview" && <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {salesReports && <Kpi label={t("reports.invoices")} slot={slot("summary")} onRetry={() => retry("summary")} value={summary?.totals?.invoice_count ?? "—"} />}
          {/* The invoices' own total (tax included, before returns) — not the
              income statement's revenue, which is on the Finance tab. */}
          {salesReports && <Kpi label={t("reports.invoicedTotal")} tone="accent" slot={slot("summary")} onRetry={() => retry("summary")} value={money(summary?.totals?.total)} />}
          {financeReports && <Kpi label={t("reports.grossProfit")} tone="ok" slot={slot("income")} onRetry={() => retry("income")} value={money(income?.gross_profit)} />}
          {inventoryReports && <Kpi label={valuationAsOf(t("reports.inventoryValue"))} slot={slot("valuation")} onRetry={() => retry("valuation")} value={money(valuation?.total_value)} />}
        </div>}

        {tab === "overview" && <div className="grid gap-6 lg:grid-cols-2">
          {salesReports && <SectionCard title={t("reports.topProductsGross")} action={<CsvLink href={csv("/reports/sales-by-product/")} />}>
            <ReportState slot={slot("byProduct")} onRetry={() => retry("byProduct")}>
              {(byProduct) => (
                <BarList items={byProduct.slice(0, 8).map((r) => ({ label: r.name, value: Number(r.revenue) }))} />
              )}
            </ReportState>
          </SectionCard>}

          {inventoryReports && <SectionCard
            title={valuationAsOf(t("reports.invValueByProduct"))}
            action={<CsvLink href={csv("/reports/inventory-valuation/", {
              method: costMethod, ...(range.end ? { as_of: range.end } : {}),
            })} />}
          >
            <ReportState slot={slot("valuation")} onRetry={() => retry("valuation")}>
              {(v) => (
                <>
                  <BarList
                    items={v.items
                      .slice()
                      .sort((a, b) => Number(b.value) - Number(a.value))
                      .slice(0, 8)
                      .map((r) => ({ label: r.name, value: Number(r.value) }))}
                  />
                  {v.as_of && v.method === "standard" && (
                    <p className="mt-3 text-xs text-muted">
                      {t("reports.valuationStandardHint", { date: v.as_of })}
                    </p>
                  )}
                </>
              )}
            </ReportState>
          </SectionCard>}
        </div>}

        {/* Profit breakdown */}
        {tab === "finance" && financeReports && <SectionCard title={t("reports.profitTitle", { method: methodName(costMethod) })}>
          <div className="grid gap-4 sm:grid-cols-3">
            <Kpi label={t("reports.revenue")} slot={slot("income")} onRetry={() => retry("income")} value={money(income?.revenue)} />
            <Kpi label={t("reports.cogs")} slot={slot("income")} onRetry={() => retry("income")} value={money(income?.cogs)} />
            <Kpi label={t("reports.grossProfit")} tone="ok" slot={slot("income")} onRetry={() => retry("income")} value={money(income?.gross_profit)} />
          </div>
          {income && (
            <p className="mt-3 text-xs text-muted">
              {t("reports.cogsMethodNote", { method: methodName(income.method) })}
            </p>
          )}
        </SectionCard>}

        {/* CFO financial KPIs — liquidity + profitability ratios */}
        {tab === "finance" && financeReports && (
          <SectionCard title={t("reports.cfoTitle")}>
            <p className="mb-3 text-xs text-muted">{t("reports.cfoHint")}</p>
            <ReportState slot={slot("kpis")} onRetry={() => retry("kpis")} isEmpty={() => false}>
              {(kpis) => (
                <>
                  <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                    <Kpi label={t("reports.grossMargin")} tone="ok" value={pct(kpis.profitability.gross_margin_pct)} />
                    <Kpi
                      label={t("reports.netMargin")}
                      tone={Number(kpis.profitability.net_profit) < 0 ? "ink" : "ok"}
                      value={pct(kpis.profitability.net_margin_pct)}
                    />
                    <Kpi label={t("reports.workingCapital")} value={money(kpis.liquidity.working_capital)} />
                    <Kpi label={t("reports.currentRatio")} value={pct(kpis.liquidity.current_ratio_pct)} />
                  </div>
                  <div className="mt-4 grid gap-4 sm:grid-cols-3">
                    <Kpi label={t("reports.receivablesOutstanding")} value={money(kpis.receivables.outstanding)} />
                    <Kpi
                      label={t("reports.receivablesOverdue")}
                      tone={Number(kpis.receivables.overdue) > 0 ? "ink" : "ok"}
                      value={money(kpis.receivables.overdue)}
                    />
                    <Kpi label={t("reports.payablesOutstanding")} value={money(kpis.payables.outstanding)} />
                  </div>
                </>
              )}
            </ReportState>
          </SectionCard>
        )}

        {/* Obligations due (AP side of the worklist) */}
        {tab === "purchasing" && purchasingReports && (
          <SectionCard title={t("reports.purchasesSummaryTitle")}>
            <ReportState slot={slot("purchases")} onRetry={() => retry("purchases")} isEmpty={() => false}>
              {(purchases) => (
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                  <div className="rounded-control bg-paper p-3"><div className="text-xs text-muted">{t("reports.purchasesTotal")}</div><div className="mt-1 tabular break-words text-xl font-semibold">{money(purchases.purchases_total)}</div></div>
                  <div className="rounded-control bg-paper p-3"><div className="text-xs text-muted">{t("reports.billCount")}</div><div className="mt-1 tabular text-xl font-semibold">{purchases.bill_count}</div></div>
                  <div className="rounded-control bg-paper p-3"><div className="text-xs text-muted">{t("reports.receiptCount")}</div><div className="mt-1 tabular text-xl font-semibold">{purchases.receipt_count}</div></div>
                </div>
              )}
            </ReportState>
          </SectionCard>
        )}
        {tab === "purchasing" && purchasingReports && (
          <SectionCard title={t("reports.apAgingTitle")}>
            <ReportState slot={slot("apAging")} onRetry={() => retry("apAging")} emptyText={t("reports.nothingOutstanding")}>
              {(rows) => agingTable(rows, "supplier", t("reports.supplier"))}
            </ReportState>
          </SectionCard>
        )}
        {tab === "purchasing" && purchasingReports && (
          <SectionCard title={t("reports.payablesDue")} action={<CsvLink href={csv("/reports/payables-due/")} />}>
            <p className="mb-3 text-xs text-muted">{t("reports.payablesHint")}</p>
            <ReportState slot={slot("payables")} onRetry={() => retry("payables")} emptyText={t("reports.noPayables")}>
              {(payables) => dueTable(payables.rows, { key: "bill", number: "reference", party: "supplier", partyLabel: t("reports.supplier") })}
            </ReportState>
          </SectionCard>
        )}

        {/* Income statement (P&L) */}
        {tab === "finance" && financeReports && (
          <SectionCard
            title={t("reports.incomeStatement")}
            action={<CsvLink href={csv("/reports/income-statement/", { method: costMethod })} />}
          >
            <ReportState slot={slot("income")} onRetry={() => retry("income")} isEmpty={() => false}>
              {(inc) => (
                <>
                  <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
                    <Kpi label={t("reports.revenue")} value={money(inc.revenue)} />
                    <Kpi label={t("reports.cogs")} value={money(inc.cogs)} />
                    <Kpi label={t("reports.grossProfit")} tone="ok" value={money(inc.gross_profit)} />
                    {/* Count differences and write-offs: a shortage is a cost
                        (positive), a surplus reduces it. Between gross and net. */}
                    <Kpi label={t("reports.stockAdjustments")} value={money(inc.stock_adjustments)} />
                    <Kpi
                      label={t("reports.netProfit")}
                      tone={Number(inc.net_profit) < 0 ? "ink" : "ok"}
                      value={money(inc.net_profit)}
                    />
                  </div>
                  <p className="mt-3 text-xs text-muted">{t("reports.stockAdjustmentsHint")}</p>
                  {inc.expenses_by_category?.length > 0 && (
                    <div className="mt-4">
                      <div className="mb-2 text-sm font-medium text-ink">
                        {t("reports.operatingExpenses")}
                      </div>
                      <BarList
                        items={inc.expenses_by_category.map((e) => ({
                          label: expenseCategory(e.category, t),
                          value: Number(e.amount),
                        }))}
                      />
                    </div>
                  )}
                </>
              )}
            </ReportState>
          </SectionCard>
        )}

        {/* Cash flow (direct method) */}
        {tab === "finance" && financeReports && (
          <SectionCard title={t("reports.cashFlow")} action={<CsvLink href={csv("/reports/cash-flow/")} />}>
            <ReportState slot={slot("cash")} onRetry={() => retry("cash")} isEmpty={() => false}>
              {(cash) => (
                <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
                  <Kpi label={t("reports.cashIn")} tone="ok" value={money(cash.inflows)} />
                  <Kpi label={t("reports.cashOutSuppliers")} value={money(cash.supplier_payments)} />
                  <Kpi label={t("reports.cashOutRefunds")} value={money(cash.customer_refunds)} />
                  <Kpi label={t("reports.cashOutExpenses")} value={money(cash.expenses)} />
                  <Kpi
                    label={t("reports.netCashFlow")}
                    tone={Number(cash.net_cash_flow) < 0 ? "ink" : "ok"}
                    value={money(cash.net_cash_flow)}
                  />
                </div>
              )}
            </ReportState>
          </SectionCard>
        )}

        {tab === "finance" && financeReports && <ZakatCard />}

        {/* Cash-flow forecast (committed documents, by week) */}
        {tab === "finance" && financeReports && (
          <SectionCard
            title={t("reports.forecastTitle")}
            action={
              <div className="flex items-center gap-2">
                <select
                  value={forecastWeeks}
                  onChange={(e) => setForecastWeeks(Number(e.target.value))}
                  className="rounded-control border border-line bg-surface px-2 py-1 text-sm text-ink"
                  aria-label={t("reports.forecastWeeks")}
                >
                  {[4, 8, 13, 26].map((w) => <option key={w} value={w}>{t("reports.forecastWeeksN", { n: w })}</option>)}
                </select>
                <CsvLink href={csv("/reports/cash-flow-forecast/", { weeks: forecastWeeks })} />
              </div>
            }
          >
            <p className="mb-3 text-xs text-muted">{t("reports.forecastHint")}</p>
            <ReportState slot={slot("forecast")} onRetry={() => retry("forecast")}>
              {(forecast) => (
                <>
                  <div className="mb-4 grid gap-4 sm:grid-cols-3">
                    <Kpi label={t("reports.forecastOverdueIn")} tone="ok" value={money(forecast.rows[0]?.inflow)} />
                    <Kpi label={t("reports.forecastOverdueOut")} value={money(forecast.rows[0]?.outflow)} />
                    <Kpi label={t("reports.forecastClosing")} tone={Number(forecast.closing_position) < 0 ? "ink" : "ok"} value={money(forecast.closing_position)} />
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-line text-xs uppercase tracking-wide text-muted">
                          <th className="px-3 py-2 text-start font-medium">{t("reports.forecastBucket")}</th>
                          <th className="px-3 py-2 text-end font-medium">{t("reports.forecastIn")}</th>
                          <th className="px-3 py-2 text-end font-medium">{t("reports.forecastOut")}</th>
                          <th className="px-3 py-2 text-end font-medium">{t("reports.forecastNet")}</th>
                          <th className="px-3 py-2 text-end font-medium">{t("reports.forecastCumulative")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {forecast.rows.map((r) => (
                          <tr key={r.bucket} className="border-b border-line last:border-0">
                            <td className="px-3 py-2">{r.bucket === "overdue" ? t("reports.forecastOverdue") : t("reports.forecastWeekFrom", { date: new Date(`${r.starts_on}T00:00:00`).toLocaleDateString(language === "ar" ? "ar" : "en", { day: "numeric", month: "short" }) })}</td>
                            <td className="tabular px-3 py-2 text-end text-ok">{cell(r.inflow)}</td>
                            <td className="tabular px-3 py-2 text-end text-danger">{cell(r.outflow)}</td>
                            <td className={`tabular px-3 py-2 text-end ${Number(r.net) < 0 ? "text-danger" : ""}`}>{cell(r.net)}</td>
                            <td className={`tabular px-3 py-2 text-end font-medium ${Number(r.cumulative) < 0 ? "text-danger" : ""}`}>{cell(r.cumulative)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </ReportState>
          </SectionCard>
        )}

        {/* Collections worklist */}
        {tab === "sales" && salesReports && (
          <SectionCard title={t("reports.collections")} action={<CsvLink href={csv("/reports/receivables-due/")} />}>
            <p className="mb-3 text-xs text-muted">{t("reports.collectionsHint")}</p>
            <ReportState slot={slot("collections")} onRetry={() => retry("collections")} emptyText={t("reports.noOverdue")}>
              {(collections) => dueTable(collections.rows, { key: "invoice", number: "number", party: "customer", partyLabel: t("reports.customer") })}
            </ReportState>
          </SectionCard>
        )}

        {/* AR aging */}
        {tab === "sales" && salesReports && (
          <SectionCard title={t("reports.arAgingTitle")}>
            <ReportState slot={slot("aging")} onRetry={() => retry("aging")} emptyText={t("reports.nothingOutstanding")}>
              {(rows) => agingTable(rows, "customer", t("reports.customer"))}
            </ReportState>
          </SectionCard>
        )}
      </div>
      <OperationalReports range={range} areas={reportAreas.filter((area) => area === tab)} />
    </div>
  );
}
