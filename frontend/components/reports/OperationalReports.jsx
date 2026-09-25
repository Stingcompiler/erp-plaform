"use client";

// The operational reports the build plan asked for alongside the financial
// ones (M5/M9): returns (sales and purchase), payment reconciliation
// (recorded vs verified) and the CRM pipeline. Each loads only for a role
// whose report areas include it — the server enforces the same map.

import { useCallback, useEffect, useState } from "react";
import { Download } from "lucide-react";

import { API_BASE, reports } from "@/lib/api";
import { useAuth } from "../../app/providers/AuthProvider";
import { useI18n } from "../../app/providers/I18nProvider";
import { Badge, Card } from "@/components/ui/kit";
import BarList from "@/components/reports/BarList";
import { SkeletonLines } from "@/components/ui/Skeleton";
import { ReportFailed } from "@/components/reports/ReportState";
import { slotFromError } from "@/lib/reportSlots";
import { formatAmount } from "@/lib/money";

function Section({ title, hint, csvHref, children }) {
  const { t } = useI18n();
  return (
    <Card className="p-5">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="font-display text-sm font-semibold uppercase tracking-wide text-muted">{title}</h2>
          {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
        </div>
        {csvHref && (
          <a href={csvHref} className="tap inline-flex h-8 items-center gap-1 rounded-control border border-line px-2.5 text-xs text-ink hover:bg-paper">
            <Download size={13} />CSV
          </a>
        )}
      </div>
      {children}
    </Card>
  );
}

function Stat({ label, value, tone = "ink" }) {
  const toneClass = { ok: "text-ok", warn: "text-warn", danger: "text-danger", ink: "text-ink" }[tone];
  return (
    <div className="rounded-control bg-paper px-3 py-2.5">
      <div className="text-xs text-muted">{label}</div>
      <div className={`tabular mt-1 text-lg font-medium ${toneClass}`}>{value}</div>
    </div>
  );
}

export default function OperationalReports({ range, areas }) {
  const { t } = useI18n();
  const { canRead } = useAuth();
  const money = (v) => formatAmount(v);
  const count = (v) => Number(v ?? 0).toLocaleString("en-US", { maximumFractionDigits: 3 });
  const pct = (v) => (v === null || v === undefined ? "—" : `${Number(v).toLocaleString("en-US", { maximumFractionDigits: 1 })}%`);
  const sales = areas.includes("sales");
  const purchasing = areas.includes("purchasing");
  const finance = areas.includes("finance");
  // Leads carry names and phone numbers: the sales report area is not
  // enough, the reader must be allowed into the CRM (the server agrees).
  const crmReport = sales && canRead("crm");

  const [salesReturns, setSalesReturns] = useState(null);
  const [purchaseReturns, setPurchaseReturns] = useState(null);
  const [reconciliation, setReconciliation] = useState(null);
  const [crm, setCrm] = useState(null);

  const params = {};
  if (range.start) params.start = range.start;
  if (range.end) params.end = range.end;
  const csv = (path) => `${API_BASE}${path}?${new URLSearchParams({ ...params, format: "csv" })}`;

  // Each card loads (and retries) on its own: null = loading, a string =
  // why it failed (lib/reportSlots), anything else = the answer.
  const fetchers = useCallback(() => {
    const p = {};
    if (range.start) p.start = range.start;
    if (range.end) p.end = range.end;
    return {
      salesReturns: [sales, () => reports.salesReturns(p), setSalesReturns],
      crm: [crmReport, () => reports.crm(p), setCrm],
      purchaseReturns: [purchasing, () => reports.purchaseReturns(p), setPurchaseReturns],
      reconciliation: [finance, () => reports.paymentReconciliation(p), setReconciliation],
    };
  }, [range.start, range.end, sales, crmReport, purchasing, finance]);

  const fetchOne = useCallback(([wanted, fetch, setter]) => {
    if (!wanted) return;
    setter(null);
    fetch().then((r) => setter(r.data)).catch((err) => setter(slotFromError(err)));
  }, []);

  useEffect(() => {
    Object.values(fetchers()).forEach(fetchOne);
  }, [fetchers, fetchOne]);

  if (!sales && !purchasing && !finance) return null;
  const body = (key, data, render) =>
    data === null ? <SkeletonLines />
      : typeof data === "string" ? <ReportFailed status={data} onRetry={() => fetchOne(fetchers()[key])} />
        : render(data);

  return (
    <div className="mt-6 grid gap-4 lg:grid-cols-2">
      {finance && (
        <div className="lg:col-span-2">
          <Section title={t("reports.ops.reconciliation")} hint={t("reports.ops.reconciliationHint")} csvHref={csv("/reports/payment-reconciliation/")}>
            {body("reconciliation", reconciliation, (d) => (
              <>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                  <Stat label={t("reports.ops.recorded")} value={`${count(d.recorded.count)} · ${money(d.recorded.amount)}`} />
                  <Stat label={t("reports.ops.verified")} value={`${count(d.verified.count)} · ${money(d.verified.amount)}`} tone="ok" />
                  <Stat label={t("reports.ops.unverified")} value={`${count(d.unverified.count)} · ${money(d.unverified.amount)}`} tone={d.unverified.count ? "warn" : "ink"} />
                  <Stat label={t("reports.ops.verifiedRate")} value={pct(d.verified_rate)} />
                </div>
                {d.oldest_unverified_days != null && (
                  <p className="mt-3 text-sm text-warn">{t("reports.ops.oldestUnverified", { days: d.oldest_unverified_days })}</p>
                )}
                {d.by_account.length > 0 && (
                  <div className="mt-4 overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-line text-xs text-muted">
                          <th className="px-2 py-2 text-start font-medium">{t("reports.ops.account")}</th>
                          <th className="px-2 py-2 text-end font-medium">{t("reports.ops.recorded")}</th>
                          <th className="px-2 py-2 text-end font-medium">{t("reports.ops.verified")}</th>
                          <th className="px-2 py-2 text-end font-medium">{t("reports.ops.unverified")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {d.by_account.map((row) => (
                          <tr key={row.account ?? "none"} className="border-b border-line last:border-0">
                            <td className="px-2 py-2 text-ink">{row.name || t(`reports.ops.method.${row.method || "cash"}`)}</td>
                            <td className="tabular px-2 py-2 text-end">{money(row.recorded)}</td>
                            <td className="tabular px-2 py-2 text-end text-ok">{money(row.verified)}</td>
                            <td className={`tabular px-2 py-2 text-end ${Number(row.unverified) ? "text-warn" : "text-muted"}`}>{money(row.unverified)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            ))}
          </Section>
        </div>
      )}

      {sales && (
        <Section title={t("reports.ops.salesReturns")} hint={t("reports.ops.salesReturnsHint")} csvHref={csv("/reports/sales-returns/")}>
          {body("salesReturns", salesReturns, (d) => (
            <>
              <div className="grid grid-cols-2 gap-2">
                <Stat label={t("reports.ops.returns")} value={count(d.return_count)} />
                <Stat label={t("reports.ops.quantity")} value={count(d.quantity)} />
                <Stat label={t("reports.ops.credited")} value={money(d.credit_total)} />
                <Stat label={t("reports.ops.refunded")} value={money(d.refund_total)} />
              </div>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {d.by_disposition.map((row) => (
                  <Badge key={row.disposition} tone={row.disposition === "scrapped" ? "danger" : row.disposition === "restocked" ? "ok" : "warn"}>
                    {t(`reports.ops.disposition.${row.disposition}`)} · {count(row.quantity)}
                  </Badge>
                ))}
              </div>
              {Number(d.written_off_total) > 0 && (
                <p className="mt-2 text-xs text-danger">{t("reports.ops.writtenOff", { amount: money(d.written_off_total) })}</p>
              )}
              <h3 className="mb-2 mt-4 text-xs font-semibold text-muted">{t("reports.ops.topReturned")}</h3>
              <BarList items={d.top_products} labelKey="name" valueKey="quantity" format={count} />
            </>
          ))}
        </Section>
      )}

      {purchasing && (
        <Section title={t("reports.ops.purchaseReturns")} hint={t("reports.ops.purchaseReturnsHint")} csvHref={csv("/reports/purchase-returns/")}>
          {body("purchaseReturns", purchaseReturns, (d) => (
            <>
              <div className="grid grid-cols-2 gap-2">
                <Stat label={t("reports.ops.returns")} value={count(d.return_count)} />
                <Stat label={t("reports.ops.debited")} value={money(d.debit_total)} />
              </div>
              <h3 className="mb-2 mt-4 text-xs font-semibold text-muted">{t("reports.ops.bySupplier")}</h3>
              <BarList items={d.by_supplier} labelKey="name" valueKey="amount" format={money} />
            </>
          ))}
        </Section>
      )}

      {crmReport && (
        <Section title={t("reports.ops.crm")} hint={t("reports.ops.crmHint")} csvHref={csv("/reports/crm/")}>
          {body("crm", crm, (d) => (
            <>
              <div className="grid grid-cols-2 gap-2">
                <Stat label={t("reports.ops.newLeads")} value={count(d.new_leads)} />
                <Stat label={t("reports.ops.pipeline")} value={money(d.pipeline_value)} />
                <Stat label={t("reports.ops.conversion")} value={pct(d.conversion_rate)} />
                <Stat label={t("reports.ops.overdueFollowUps")} value={count(d.follow_ups.overdue)} tone={d.follow_ups.overdue ? "warn" : "ink"} />
              </div>
              <h3 className="mb-2 mt-4 text-xs font-semibold text-muted">{t("reports.ops.byStage")}</h3>
              <BarList
                items={d.stages.map((row) => ({ ...row, label: t(`reports.ops.stage.${row.stage}`) }))}
                valueKey="count"
                format={count}
              />
            </>
          ))}
        </Section>
      )}
    </div>
  );
}
