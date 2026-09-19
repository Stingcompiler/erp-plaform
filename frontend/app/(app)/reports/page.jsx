"use client";

import { useCallback, useEffect, useState } from "react";
import { Download, Lock } from "lucide-react";

import { API_BASE, reports } from "@/lib/api";
import { useAuth } from "../../providers/AuthProvider";
import { useI18n } from "../../providers/I18nProvider";
import { Badge, Button, Card, Field, Input, PageHeader, Select } from "@/components/ui/kit";
import BarList from "@/components/reports/BarList";
import ZakatCard from "@/components/reports/ZakatCard";

function Kpi({ label, value, tone = "ink" }) {
  const toneClass = tone === "accent" ? "text-accent" : tone === "ok" ? "text-ok" : "text-ink";
  return (
    <Card className="p-5">
      <div className="text-sm text-muted">{label}</div>
      <div className={`tabular mt-2 text-2xl font-medium ${toneClass}`}>{value}</div>
    </Card>
  );
}

function SectionCard({ title, action, children }) {
  return (
    <Card className="p-5">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="font-display text-sm font-semibold uppercase tracking-wide text-muted">
          {title}
        </h2>
        {action}
      </div>
      {children}
    </Card>
  );
}

export default function ReportsPage() {
  const { canRead, user } = useAuth();
  const { t, language } = useI18n();
  const reportAreas = user?.report_areas || [];
  const salesReports = reportAreas.includes("sales");
  const inventoryReports = reportAreas.includes("inventory");
  const purchasingReports = reportAreas.includes("purchasing");
  const financeReports = reportAreas.includes("finance");
  const hrReports = reportAreas.includes("hr");
  const payrollReports = hrReports || financeReports;
  const onlyHrReports = hrReports && reportAreas.length === 1;
  const money = (v) =>
    Number(v ?? 0).toLocaleString(language === "ar" ? "ar" : "en", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  // Ratios are null when undefined (zero denominator) — show a dash rather
  // than 0%, which would read as a real measurement.
  const pct = (v) =>
    v === null || v === undefined
      ? t("reports.undefinedRatio")
      : `${Number(v).toLocaleString(language === "ar" ? "ar" : "en", {
          maximumFractionDigits: 1,
        })}%`;
  const [range, setRange] = useState({ start: "", end: "" });
  const [costMethod, setCostMethod] = useState("standard");
  const [summary, setSummary] = useState(null);
  const [byProduct, setByProduct] = useState([]);
  const [valuation, setValuation] = useState(null);
  const [aging, setAging] = useState([]);
  const [profit, setProfit] = useState(null);
  const [income, setIncome] = useState(null);
  const [cash, setCash] = useState(null);
  const [forecast, setForecast] = useState(null);
  const [forecastWeeks, setForecastWeeks] = useState(8);
  const [collections, setCollections] = useState(null);
  const [kpis, setKpis] = useState(null);
  const [payables, setPayables] = useState(null);
  const [apAging, setApAging] = useState([]);
  const [purchases, setPurchases] = useState(null);
  const [hrSummary, setHrSummary] = useState(null);
  const [payroll, setPayroll] = useState([]);
  const [loading, setLoading] = useState(true);

  const params = {};
  if (range.start) params.start = range.start;
  if (range.end) params.end = range.end;

  const load = useCallback(async () => {
    setLoading(true);
    const p = {};
    if (range.start) p.start = range.start;
    if (range.end) p.end = range.end;
    const settle = (promise, setter, fallback) =>
      promise.then((r) => setter(r.data)).catch(() => setter(fallback));
    await Promise.all([
      ...(salesReports ? [
        settle(reports.salesSummary(p), setSummary, null),
        settle(reports.salesByProduct(p), setByProduct, []),
        settle(reports.arAging(), setAging, []),
        settle(reports.receivablesDue(), setCollections, null),
      ] : []),
      ...(inventoryReports ? [
        settle(reports.inventoryValuation({ method: costMethod }), setValuation, null),
      ] : []),
      ...(purchasingReports ? [
        settle(reports.payablesDue(), setPayables, null),
        settle(reports.apAging(), setApAging, []),
        settle(reports.purchasesSummary(p), setPurchases, null),
      ] : []),
      ...(financeReports ? [
        settle(reports.profitSummary({ ...p, method: costMethod }), setProfit, null),
        settle(reports.incomeStatement({ ...p, method: costMethod }), setIncome, null),
        settle(reports.cashFlow(p), setCash, null),
        settle(reports.cashFlowForecast({ weeks: forecastWeeks }), setForecast, null),
        settle(reports.cfoKpis({ ...p, method: costMethod }), setKpis, null),
      ] : []),
      ...(hrReports ? [settle(reports.hrSummary(p), setHrSummary, null)] : []),
      ...(payrollReports ? [settle(reports.payroll(p), setPayroll, [])] : []),
    ]);
    setLoading(false);
  }, [range.start, range.end, costMethod, salesReports, inventoryReports, purchasingReports, financeReports, hrReports, payrollReports, forecastWeeks]);

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

  const csv = (path, extra = {}) => {
    const qs = new URLSearchParams({ ...params, ...extra, format: "csv" }).toString();
    return `${API_BASE}${path}?${qs}`;
  };

  const productBars = byProduct.slice(0, 8).map((r) => ({
    label: r.name,
    value: Number(r.revenue),
  }));
  const valuationBars = (valuation?.items || [])
    .slice()
    .sort((a, b) => Number(b.value) - Number(a.value))
    .slice(0, 8)
    .map((r) => ({ label: r.name, value: Number(r.value) }));

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
          <Button variant="outline" onClick={() => setRange({ start: "", end: "" })}>
            {t("reports.allTime")}
          </Button>
          {(inventoryReports || financeReports) && <div className="ms-auto">
            <Field label={t("reports.costingMethod")}>
              <Select value={costMethod} onChange={(e) => setCostMethod(e.target.value)}>
                <option value="standard">{t("reports.standardCost")}</option>
                <option value="average">{t("reports.weightedAverage")}</option>
                <option value="fifo">{t("reports.fifo")}</option>
              </Select>
            </Field>
          </div>}
        </div>
      </Card>

      {loading && <div className="text-muted">{t("reports.loadingReports")}</div>}

      {!loading && (
        <div className="space-y-6">
          {hrReports && hrSummary && (
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
                <BarList items={hrSummary.departments.map((row) => ({ label: row.name, value: row.count }))} />
              </SectionCard>
            </>
          )}

          {payrollReports && <SectionCard title={t("reports.payrollTitle")} action={<a href={csv("/reports/payroll/")}><Button variant="ghost"><Download size={15} /> CSV</Button></a>}>
            {payroll.length === 0 ? <p className="text-sm text-muted">{t("reports.noPayroll")}</p> : <div className="space-y-4">{payroll.map((run) => <div key={run.id} className="rounded-control border border-line p-4"><div className="mb-3 flex flex-wrap items-center justify-between gap-2"><div className="font-medium text-ink">{t("reports.payrollFor", { period: run.period.slice(0, 7) })}</div><Badge tone={run.status === "approved" ? "ok" : "warn"}>{run.status === "approved" ? t("hr.approved") : t("hr.pending")}</Badge></div><div className="grid gap-3 sm:grid-cols-4"><Kpi label={t("reports.payrollEmployees")} value={run.employee_count} /><Kpi label={t("reports.payrollBase")} value={money(run.base_total)} /><Kpi label={t("reports.payrollDeductions")} value={money(run.deductions_total)} /><Kpi label={t("reports.payrollNet")} tone="ok" value={money(run.net_total)} /></div><div className="mt-3 divide-y divide-line text-sm">{run.entries.map((entry) => <div key={`${run.id}-${entry.employee_name}`} className="flex flex-wrap items-center justify-between gap-2 py-2"><span className="text-ink">{entry.employee_name} <span className="text-muted">· {entry.department_name || "—"} · {entry.position_title || "—"}</span></span><span className="tabular font-medium">{money(entry.net_salary)}</span></div>)}</div></div>)}</div>}
          </SectionCard>}

          {/* Headline KPIs */}
          {!onlyHrReports && <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {salesReports && <Kpi label={t("reports.invoices")} value={summary?.totals?.invoice_count ?? "—"} />}
            {salesReports && <Kpi label={t("reports.revenue")} tone="accent" value={money(summary?.totals?.total)} />}
            {financeReports && <Kpi label={t("reports.grossProfit")} tone="ok" value={money(profit?.gross_profit)} />}
            {inventoryReports && <Kpi label={t("reports.inventoryValue")} value={money(valuation?.total_value)} />}
          </div>}

          <div className="grid gap-6 lg:grid-cols-2">
            {salesReports && <SectionCard
              title={t("reports.topProducts")}
              action={
                <a href={csv("/reports/sales-by-product/")}>
                  <Button variant="ghost">
                    <Download size={15} /> CSV
                  </Button>
                </a>
              }
            >
              <BarList items={productBars} />
            </SectionCard>}

            {inventoryReports && <SectionCard
              title={t("reports.invValueByProduct")}
              action={
                <a href={csv("/reports/inventory-valuation/", { method: costMethod })}>
                  <Button variant="ghost">
                    <Download size={15} /> CSV
                  </Button>
                </a>
              }
            >
              <BarList items={valuationBars} />
            </SectionCard>}
          </div>

          {/* Profit breakdown */}
          {financeReports && <SectionCard
            title={t("reports.profitTitle", {
              method: {
                standard: t("reports.standardCost"),
                average: t("reports.weightedAverage"),
                fifo: t("reports.fifo"),
              }[costMethod],
            })}
          >
            <div className="grid gap-4 sm:grid-cols-3">
              <Kpi label={t("reports.revenue")} value={money(profit?.revenue)} />
              <Kpi label={t("reports.cogs")} value={money(profit?.cogs ?? profit?.cogs_standard_cost)} />
              <Kpi label={t("reports.grossProfit")} tone="ok" value={money(profit?.gross_profit)} />
            </div>
            {profit?.note && <p className="mt-3 text-xs text-muted">{profit.note}</p>}
          </SectionCard>}

          {/* CFO financial KPIs — liquidity + profitability ratios */}
          {financeReports && kpis && (
            <SectionCard title={t("reports.cfoTitle")}>
              <p className="mb-3 text-xs text-muted">{t("reports.cfoHint")}</p>
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                <Kpi
                  label={t("reports.grossMargin")}
                  tone="ok"
                  value={pct(kpis.profitability.gross_margin_pct)}
                />
                <Kpi
                  label={t("reports.netMargin")}
                  tone={Number(kpis.profitability.net_profit) < 0 ? "ink" : "ok"}
                  value={pct(kpis.profitability.net_margin_pct)}
                />
                <Kpi
                  label={t("reports.workingCapital")}
                  value={money(kpis.liquidity.working_capital)}
                />
                <Kpi
                  label={t("reports.currentRatio")}
                  value={pct(kpis.liquidity.current_ratio_pct)}
                />
              </div>
              <div className="mt-4 grid gap-4 sm:grid-cols-3">
                <Kpi
                  label={t("reports.receivablesOutstanding")}
                  value={money(kpis.receivables.outstanding)}
                />
                <Kpi
                  label={t("reports.receivablesOverdue")}
                  tone={Number(kpis.receivables.overdue) > 0 ? "ink" : "ok"}
                  value={money(kpis.receivables.overdue)}
                />
                <Kpi
                  label={t("reports.payablesOutstanding")}
                  value={money(kpis.payables.outstanding)}
                />
              </div>
            </SectionCard>
          )}

          {/* Obligations due (AP side of the worklist) */}
          {purchasingReports && purchases && (
            <SectionCard title={t("reports.purchasesSummaryTitle")}>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                <div className="rounded-control bg-paper p-3"><div className="text-xs text-muted">{t("reports.purchasesTotal")}</div><div className="mt-1 tabular text-xl font-semibold">{money(purchases.purchases_total)}</div></div>
                <div className="rounded-control bg-paper p-3"><div className="text-xs text-muted">{t("reports.billCount")}</div><div className="mt-1 tabular text-xl font-semibold">{purchases.bill_count}</div></div>
                <div className="rounded-control bg-paper p-3"><div className="text-xs text-muted">{t("reports.receiptCount")}</div><div className="mt-1 tabular text-xl font-semibold">{purchases.receipt_count}</div></div>
              </div>
            </SectionCard>
          )}
          {purchasingReports && (
            <SectionCard title={t("reports.apAgingTitle")}>
              {apAging.length === 0 ? (
                <p className="py-6 text-center text-sm text-muted">{t("reports.nothingOutstanding")}</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-line text-xs uppercase tracking-wide text-muted">
                        <th className="px-3 py-2 text-start font-medium">{t("reports.supplier")}</th>
                        <th className="px-3 py-2 text-end font-medium">{t("reports.current")}</th>
                        <th className="px-3 py-2 text-end font-medium">1–30</th>
                        <th className="px-3 py-2 text-end font-medium">31–60</th>
                        <th className="px-3 py-2 text-end font-medium">61–90</th>
                        <th className="px-3 py-2 text-end font-medium">{t("reports.over90")}</th>
                        <th className="px-3 py-2 text-end font-medium">{t("common.total")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {apAging.map((row) => (
                        <tr key={row.supplier} className="border-b border-line last:border-0">
                          <td className="px-3 py-2 text-ink">{row.name}</td>
                          <td className="tabular px-3 py-2 text-end text-muted">{money(row.current)}</td>
                          <td className="tabular px-3 py-2 text-end text-muted">{money(row["1_30"])}</td>
                          <td className="tabular px-3 py-2 text-end text-muted">{money(row["31_60"])}</td>
                          <td className="tabular px-3 py-2 text-end text-muted">{money(row["61_90"])}</td>
                          <td className="tabular px-3 py-2 text-end text-warn">{money(row.over_90)}</td>
                          <td className="tabular px-3 py-2 text-end font-medium text-ink">{money(row.total)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </SectionCard>
          )}
          {purchasingReports && payables && (
            <SectionCard
              title={t("reports.payablesDue")}
              action={
                <a href={csv("/reports/payables-due/")}>
                  <Button variant="ghost">
                    <Download size={15} /> CSV
                  </Button>
                </a>
              }
            >
              <p className="mb-3 text-xs text-muted">{t("reports.payablesHint")}</p>
              {payables.rows.length === 0 ? (
                <p className="py-6 text-center text-sm text-muted">{t("reports.noPayables")}</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-line text-xs uppercase tracking-wide text-muted">
                        <th className="px-3 py-2 text-start font-medium">{t("reports.invoiceNo")}</th>
                        <th className="px-3 py-2 text-start font-medium">{t("reports.supplier")}</th>
                        <th className="px-3 py-2 text-start font-medium">{t("reports.dueDate")}</th>
                        <th className="px-3 py-2 text-end font-medium">{t("reports.daysOverdue")}</th>
                        <th className="px-3 py-2 text-end font-medium">{t("reports.amountDue")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {payables.rows.map((r) => (
                        <tr key={r.bill} className="border-b border-line last:border-0">
                          <td className="tabular px-3 py-2 text-ink">{r.reference}</td>
                          <td className="px-3 py-2 text-muted">{r.supplier}</td>
                          <td className="tabular px-3 py-2 text-muted">{r.due_date || "—"}</td>
                          <td className="px-3 py-2 text-end">
                            {r.days_overdue > 0 ? (
                              <Badge tone="danger">{r.days_overdue}</Badge>
                            ) : (
                              <Badge tone="muted">{t("reports.dueSoon")}</Badge>
                            )}
                          </td>
                          <td className="tabular px-3 py-2 text-end font-medium text-ink">
                            {money(r.amount_due)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </SectionCard>
          )}

          {/* Income statement (P&L) */}
          {financeReports && income && (
            <SectionCard
              title={t("reports.incomeStatement")}
              action={
                <a href={csv("/reports/income-statement/", { method: costMethod })}>
                  <Button variant="ghost">
                    <Download size={15} /> CSV
                  </Button>
                </a>
              }
            >
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                <Kpi label={t("reports.revenue")} value={money(income.revenue)} />
                <Kpi label={t("reports.cogs")} value={money(income.cogs)} />
                <Kpi label={t("reports.grossProfit")} tone="ok" value={money(income.gross_profit)} />
                <Kpi
                  label={t("reports.netProfit")}
                  tone={Number(income.net_profit) < 0 ? "ink" : "ok"}
                  value={money(income.net_profit)}
                />
              </div>
              {income.expenses_by_category?.length > 0 && (
                <div className="mt-4">
                  <div className="mb-2 text-sm font-medium text-ink">
                    {t("reports.operatingExpenses")}
                  </div>
                  <BarList
                    items={income.expenses_by_category.map((e) => ({
                      label: e.category,
                      value: Number(e.amount),
                    }))}
                    format={money}
                  />
                </div>
              )}
            </SectionCard>
          )}

          {/* Cash flow (direct method) */}
          {financeReports && cash && (
            <SectionCard
              title={t("reports.cashFlow")}
              action={
                <a href={csv("/reports/cash-flow/")}>
                  <Button variant="ghost">
                    <Download size={15} /> CSV
                  </Button>
                </a>
              }
            >
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                <Kpi label={t("reports.cashIn")} tone="ok" value={money(cash.inflows)} />
                <Kpi label={t("reports.cashOutSuppliers")} value={money(cash.supplier_payments)} />
                <Kpi label={t("reports.cashOutExpenses")} value={money(cash.expenses)} />
                <Kpi
                  label={t("reports.netCashFlow")}
                  tone={Number(cash.net_cash_flow) < 0 ? "ink" : "ok"}
                  value={money(cash.net_cash_flow)}
                />
              </div>
            </SectionCard>
          )}

          {financeReports && <ZakatCard />}

          {/* Cash-flow forecast (committed documents, by week) */}
          {financeReports && forecast && (
            <SectionCard
              title={t("reports.forecastTitle")}
              action={
                <div className="flex items-center gap-2">
                  <select
                    value={forecastWeeks}
                    onChange={(e) => setForecastWeeks(Number(e.target.value))}
                    className="rounded-control border border-line bg-surface px-2 py-1 text-sm"
                    aria-label={t("reports.forecastWeeks")}
                  >
                    {[4, 8, 13, 26].map((w) => <option key={w} value={w}>{t("reports.forecastWeeksN", { n: w })}</option>)}
                  </select>
                  <a href={csv("/reports/cash-flow-forecast/", { weeks: forecastWeeks })}>
                    <Button variant="ghost">
                      <Download size={15} /> CSV
                    </Button>
                  </a>
                </div>
              }
            >
              <p className="mb-3 text-xs text-muted">{t("reports.forecastHint")}</p>
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
                        <td className="tabular px-3 py-2 text-end text-ok">{money(r.inflow)}</td>
                        <td className="tabular px-3 py-2 text-end text-danger">{money(r.outflow)}</td>
                        <td className={`tabular px-3 py-2 text-end ${Number(r.net) < 0 ? "text-danger" : ""}`}>{money(r.net)}</td>
                        <td className={`tabular px-3 py-2 text-end font-medium ${Number(r.cumulative) < 0 ? "text-danger" : ""}`}>{money(r.cumulative)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </SectionCard>
          )}

          {/* Collections worklist */}
          {salesReports && collections && (
            <SectionCard
              title={t("reports.collections")}
              action={
                <a href={csv("/reports/receivables-due/")}>
                  <Button variant="ghost">
                    <Download size={15} /> CSV
                  </Button>
                </a>
              }
            >
              <p className="mb-3 text-xs text-muted">{t("reports.collectionsHint")}</p>
              {collections.rows.length === 0 ? (
                <p className="py-6 text-center text-sm text-muted">{t("reports.noOverdue")}</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-line text-xs uppercase tracking-wide text-muted">
                        <th className="px-3 py-2 text-start font-medium">{t("reports.invoiceNo")}</th>
                        <th className="px-3 py-2 text-start font-medium">{t("reports.customer")}</th>
                        <th className="px-3 py-2 text-start font-medium">{t("reports.dueDate")}</th>
                        <th className="px-3 py-2 text-end font-medium">{t("reports.daysOverdue")}</th>
                        <th className="px-3 py-2 text-end font-medium">{t("reports.amountDue")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {collections.rows.map((r) => (
                        <tr key={r.invoice} className="border-b border-line last:border-0">
                          <td className="tabular px-3 py-2 text-ink">{r.number}</td>
                          <td className="px-3 py-2 text-muted">{r.customer}</td>
                          <td className="tabular px-3 py-2 text-muted">{r.due_date || "—"}</td>
                          <td className="px-3 py-2 text-end">
                            {r.days_overdue > 0 ? (
                              <Badge tone="danger">{r.days_overdue}</Badge>
                            ) : (
                              <Badge tone="muted">{t("reports.dueSoon")}</Badge>
                            )}
                          </td>
                          <td className="tabular px-3 py-2 text-end font-medium text-ink">
                            {money(r.amount_due)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </SectionCard>
          )}

          {/* AR aging */}
          {salesReports && <SectionCard title={t("reports.arAgingTitle")}>
            {aging.length === 0 ? (
              <p className="py-6 text-center text-sm text-muted">{t("reports.nothingOutstanding")}</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-line text-xs uppercase tracking-wide text-muted">
                      <th className="px-3 py-2 text-start font-medium">{t("reports.customer")}</th>
                      <th className="px-3 py-2 text-end font-medium">{t("reports.current")}</th>
                      <th className="px-3 py-2 text-end font-medium">1–30</th>
                      <th className="px-3 py-2 text-end font-medium">31–60</th>
                      <th className="px-3 py-2 text-end font-medium">61–90</th>
                      <th className="px-3 py-2 text-end font-medium">{t("reports.over90")}</th>
                      <th className="px-3 py-2 text-end font-medium">{t("common.total")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {aging.map((row) => (
                      <tr key={row.customer} className="border-b border-line last:border-0">
                        <td className="px-3 py-2 text-ink">{row.name}</td>
                        <td className="tabular px-3 py-2 text-end text-muted">{money(row.current)}</td>
                        <td className="tabular px-3 py-2 text-end text-muted">{money(row["1_30"])}</td>
                        <td className="tabular px-3 py-2 text-end text-muted">{money(row["31_60"])}</td>
                        <td className="tabular px-3 py-2 text-end text-muted">{money(row["61_90"])}</td>
                        <td className="tabular px-3 py-2 text-end text-warn">{money(row.over_90)}</td>
                        <td className="tabular px-3 py-2 text-end font-medium text-ink">
                          {money(row.total)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </SectionCard>}
        </div>
      )}
    </div>
  );
}
