"use client";

import { useEffect, useState } from "react";
import {
  AlertTriangle,
  Boxes,
  CalendarClock,
  Contact,
  Globe,
  LayoutList,
  Package,
  Receipt,
  RotateCcw,
  Scale,
  TrendingDown,
  UsersRound,
  UserPlus,
  Wallet,
} from "lucide-react";

import Link from "next/link";
import { Button, PageHeader } from "@/components/ui/kit";

import { dashboard } from "@/lib/api";
import { useAuth } from "../../providers/AuthProvider";
import { useI18n } from "../../providers/I18nProvider";
import { translateRole } from "@/lib/i18n";
import BarList from "@/components/reports/BarList";
import { SkeletonCard } from "@/components/ui/Skeleton";

function Stat({ icon: Icon, label, value, tone = "ink", sub }) {
  const toneClass =
    tone === "warn" ? "text-warn" : tone === "ok" ? "text-ok" : tone === "accent" ? "text-accent" : "text-ink";
  return (
    <div className="dashboard-stat rounded-card border border-line bg-surface p-4 shadow-card sm:p-5">
      <div className="flex items-center gap-2 text-muted">
        <span className={`grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-paper ${toneClass}`}><Icon size={17} strokeWidth={1.8} /></span>
        <span className="text-sm">{label}</span>
      </div>
      <div className={`tabular mt-3 break-words text-2xl font-semibold sm:text-3xl ${toneClass}`}>{value}</div>
      {sub && <div className="mt-1 text-xs text-muted">{sub}</div>}
    </div>
  );
}

function Section({ title, children }) {
  return (
    <section className="dashboard-section">
      <h2 className="mb-4 font-display text-base font-bold text-ink">
        {title}
      </h2>
      <div className="grid grid-cols-2 gap-3">{children}</div>
    </section>
  );
}

export default function DashboardPage() {
  const { user, canWrite, canRead, can } = useAuth();
  const { t, language } = useI18n();
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  const [advanceAlertDismissed, setAdvanceAlertDismissed] = useState(false);

  const money = (v) =>
    Number(v ?? 0).toLocaleString(language === "ar" ? "ar" : "en", {
      maximumFractionDigits: 2,
    });

  const load = () => {
    setError(false);
    dashboard
      .get()
      .then((res) => setData(res.data))
      .catch(() => setError(true));
  };
  useEffect(() => { load(); }, []);

  const sections = data?.sections || {};
  const advanceRequestSignature = sections.advance_requests
    ? JSON.stringify(sections.advance_requests)
    : "";

  useEffect(() => {
    if (!advanceRequestSignature || !user?.id || !user?.company) {
      setAdvanceAlertDismissed(false);
      return;
    }
    const key = `vezano.advance-request-alert:${user.company}:${user.id}`;
    setAdvanceAlertDismissed(window.localStorage.getItem(key) === advanceRequestSignature);
  }, [advanceRequestSignature, user?.company, user?.id]);

  // The setup checklist can be put away (a one-person shop never "adds a
  // team"); it is a per-person convenience, so browser storage is enough.
  const setupKey = user?.id && user?.company ? `vezano.setup-hidden:${user.company}:${user.id}` : "";
  const [setupHidden, setSetupHidden] = useState(false);
  useEffect(() => {
    if (!setupKey) return;
    try { setSetupHidden(window.localStorage.getItem(setupKey) === "1"); } catch { /* storage blocked */ }
  }, [setupKey]);
  const hideSetup = () => {
    setSetupHidden(true);
    try { window.localStorage.setItem(setupKey, "1"); } catch { /* storage blocked */ }
  };
  const setupTotal = data?.setup?.length || 1;
  const setupDone = data?.setup?.filter((step) => step.done).length || 0;

  const dismissAdvanceRequestAlert = () => {
    const key = `vezano.advance-request-alert:${user.company}:${user.id}`;
    window.localStorage.setItem(key, advanceRequestSignature);
    setAdvanceAlertDismissed(true);
  };

  return (
    <div>
      <div className="dashboard-hero mb-6 rounded-card border border-line p-5 sm:p-7">
        <div className="mb-3 flex items-center gap-2 text-xs font-semibold text-accent"><span className="h-1.5 w-1.5 rounded-full bg-accent" />{user?.company_name || t("shell.workspace")}</div>
        <PageHeader title={t("dashboard.title")}
          subtitle={language === "ar" ? "صورة واضحة لأعمالك، وخطوتك التالية في مكان واحد." : "A clear view of your business. Your next action, all in one place."}
          actions={<span className="rounded-full border border-line bg-surface px-3 py-1.5 text-xs text-muted">{translateRole(user?.role_name, t)}</span>} />
      </div>

      {error && (
        <div className="mt-6 rounded-card border border-line bg-surface p-6 text-muted">
          <p role="alert">{t("dashboard.loadError")}</p><Button className="mt-3" onClick={load}>{t("improvements.retry")}</Button>
        </div>
      )}

      {!data && !error && <SkeletonCard className="mt-6" />}

      {data && (
        <div className="dashboard-overview">
          {data.setup?.some((step) => !step.done) && !setupHidden && <section className="mb-6 rounded-card border border-accent/30 bg-surface p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <h2 className="font-display text-lg font-semibold">{t("improvements.checklist")}</h2>
                <p className="mt-1 text-sm text-muted">{t("improvements.checklistHint")}</p>
              </div>
              <Button variant="ghost" onClick={hideSetup}>{t("improvements.checklistHide")}</Button>
            </div>
            <div className="mt-4 flex items-center gap-3">
              <div className="h-2 flex-1 overflow-hidden rounded-full bg-line" role="progressbar" aria-valuemin={0} aria-valuemax={setupTotal} aria-valuenow={setupDone}>
                <div className="h-full rounded-full bg-accent transition-all" style={{ width: `${(setupDone / setupTotal) * 100}%` }} />
              </div>
              <span className="shrink-0 text-xs font-medium text-muted">{t("improvements.checklistProgress", { done: setupDone, total: setupTotal })}</span>
            </div>
            <ol className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{data.setup.map((step,index) =>
              <li key={step.key}><Link href={step.href} className="block h-full rounded-control border border-line p-3 hover:border-accent">
                <span className={step.done ? "text-ok" : "text-muted"}>{step.done ? "✓" : index+1}</span>
                <span className="mt-2 block text-sm font-medium">{t(`improvements.${step.key}`)}</span>
                <span className="mt-1 block text-xs text-muted">{t(step.done ? "improvements.done" : "improvements.openStep")}</span>
              </Link></li>)}</ol>
          </section>}
          <section className="mb-6">
            <h2 className="mb-3 font-display text-sm font-semibold text-muted">{t("improvements.quickActions")}</h2>
            <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
              {canWrite("sales") && <Link className="flex min-h-12 items-center justify-center rounded-control bg-accent px-4 py-3 text-sm font-medium text-white" href="/sales?tab=pos">{t("improvements.newSale")}</Link>}
              {canWrite("purchasing") && <Link className="flex min-h-12 items-center justify-center rounded-control border border-line bg-surface px-4 py-3 transition-colors hover:border-accent/50 hover:bg-accent/5 text-sm" href="/purchasing?tab=receive">{t("improvements.receiveStock")}</Link>}
              {canRead("inventory") && <Link className="flex min-h-12 items-center justify-center rounded-control border border-line bg-surface px-4 py-3 transition-colors hover:border-accent/50 hover:bg-accent/5 text-sm" href="/inventory?low_stock=1">{t("dashboard.lowStock")} · {sections.inventory?.low_stock_count ?? "—"}</Link>}
              {canRead("inventory") && sections.inventory?.negative_stock_count > 0 && <Link className="flex min-h-12 items-center justify-center rounded-control border border-danger/40 bg-danger/5 px-4 py-3 text-sm text-danger transition-colors hover:border-danger" href="/inventory?negative=1">{t("dashboard.negativeStock")} · {sections.inventory.negative_stock_count}</Link>}
              {canRead("sales_returns") && <Link className="flex min-h-12 items-center justify-center rounded-control border border-line bg-surface px-4 py-3 transition-colors hover:border-accent/50 hover:bg-accent/5 text-sm" href="/returns">{t("improvements.reviewReturns")} · {sections.returns?.pending_disposition_count ?? "—"}</Link>}
              {can("users.assign_owner") && <Link className="flex min-h-12 items-center justify-center gap-2 rounded-control border border-accent/30 bg-accent/5 px-4 py-3 text-sm font-medium text-accent transition-colors hover:border-accent" href="/users"><UserPlus size={16} />{t("users.manageOwners")}</Link>}
            </div>
          </section>
          {sections.salary_advances?.pending_count > 0 && (
            <Link
              href="/hr?tab=advances"
              className="mb-6 flex items-center justify-between gap-4 rounded-card border border-warn/30 bg-warn/10 p-5 transition-colors hover:border-warn/60"
            >
              <div className="flex min-w-0 items-start gap-3">
                <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-warn/20 text-warn">
                  <AlertTriangle size={20} />
                </span>
                <div>
                  <h2 className="font-display text-base font-bold text-ink">{t("dashboard.pendingAdvancesTitle")}</h2>
                  <p className="mt-1 text-sm text-muted">
                    {t("dashboard.pendingAdvancesMessage", { count: sections.salary_advances.pending_count })}
                  </p>
                </div>
              </div>
              <span className="shrink-0 text-sm font-semibold text-warn">{t("dashboard.reviewAdvances")}</span>
            </Link>
          )}
          {sections.advance_requests && !advanceAlertDismissed && (
            <Link
              href="/hr?tab=advances"
              onClick={dismissAdvanceRequestAlert}
              className="mb-6 flex items-center justify-between gap-4 rounded-card border border-accent/25 bg-accent/5 p-5 transition-colors hover:border-accent/50"
            >
              <div className="flex min-w-0 items-start gap-3">
                <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-accent/10 text-accent">
                  <Wallet size={20} />
                </span>
                <div>
                  <h2 className="font-display text-base font-bold text-ink">{t("dashboard.advanceRequestStatus")}</h2>
                  <p className="mt-1 text-sm text-muted">
                    {t("dashboard.advanceRequestMessage", sections.advance_requests)}
                  </p>
                </div>
              </div>
              <span className="shrink-0 text-sm font-semibold text-accent">{t("dashboard.viewAdvanceRequests")}</span>
            </Link>
          )}
          {sections.sales && <div className="mb-6 grid grid-cols-2 gap-3">
            <Link href="/sales?tab=invoices"><Stat icon={Receipt} label={t("improvements.todaySales")} value={money(sections.sales.today_total)} sub={data.currency} tone="accent" /></Link>
            <Link href="/sales?tab=invoices&overdue=1"><Stat icon={CalendarClock} label={t("improvements.overdue")} value={sections.sales.overdue_count} /></Link>
          </div>}
          {sections.sales && (
            <Section title={t("dashboard.sales")}>
              <Stat
                icon={Receipt}
                label={t("dashboard.invoices")}
                value={sections.sales.invoice_count}
              />
              <Stat
                icon={Wallet}
                label={t("dashboard.revenueMonth")}
                tone="accent"
                value={money(sections.sales.revenue_total)}
              />
            </Section>
          )}

          {sections.debts && (
            <section className="mt-8">
              <div className="mb-4 flex items-center justify-between gap-3">
                <h2 className="font-display text-base font-bold text-ink">{t("dashboard.debtLedger")}</h2>
                <Link href="/debts" className="tap inline-flex items-center text-sm font-medium text-accent hover:underline">{t("common.view")}</Link>
              </div>
              <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
                <Link href="/debts"><Stat icon={Wallet} label={t("dashboard.outstandingReceivables")} tone="accent" value={money(sections.debts.outstanding)} /></Link>
                <Link href="/debts?status=overdue"><Stat icon={AlertTriangle} label={t("dashboard.overdueReceivables")} tone={Number(sections.debts.overdue) > 0 ? "warn" : "ink"} value={money(sections.debts.overdue)} /></Link>
                <Link href="/debts?status=owing"><Stat icon={UsersRound} label={t("dashboard.customersOwing")} value={sections.debts.debtor_count} /></Link>
                <Link href="/debts?status=credit"><Stat icon={Wallet} label={t("dashboard.customerCredit")} tone="ok" value={money(sections.debts.credit_balance)} /></Link>
              </div>
            </section>
          )}

          {/* Chart — this month's top products by invoiced amount (gross,
              before returns), scoped like the sales totals above. */}
          {sections.sales?.top_products?.length > 0 && (
            <section className="mt-8">
              <h2 className="mb-4 font-display text-base font-bold text-ink">
                {t("dashboard.topProductsMonth")}
              </h2>
              <div className="dashboard-stat rounded-card border border-line bg-surface p-4 shadow-card sm:p-5">
                <BarList
                  items={sections.sales.top_products.map((p) => ({
                    label: p.label,
                    value: Number(p.value),
                  }))}
                  format={money}
                />
              </div>
            </section>
          )}

          {sections.inventory && (
            <Section title={t("dashboard.inventory")}>
              <Stat
                icon={Package}
                label={t("dashboard.products")}
                value={sections.inventory.product_count}
              />
              <Stat
                icon={AlertTriangle}
                label={t("dashboard.lowStock")}
                tone={sections.inventory.low_stock_count > 0 ? "warn" : "ink"}
                value={sections.inventory.low_stock_count}
                sub={sections.inventory.low_stock_count > 0 ? undefined : t("dashboard.aboveReorder")}
              />
              <Stat
                icon={AlertTriangle}
                label={t("dashboard.expiringBatches")}
                tone={sections.inventory.expiring_batch_count > 0 ? "warn" : "ink"}
                value={sections.inventory.expiring_batch_count ?? 0}
              />
              <Stat
                icon={AlertTriangle}
                label={t("dashboard.negativeStock")}
                tone={sections.inventory.negative_stock_count > 0 ? "danger" : "ink"}
                value={sections.inventory.negative_stock_count ?? 0}
              />
            </Section>
          )}

          {sections.purchasing && (
            <Section title={t("dashboard.purchasing")}>
              <Stat
                icon={Boxes}
                label={t("dashboard.suppliers")}
                value={sections.purchasing.supplier_count}
              />
              <Stat
                icon={Receipt}
                label={t("dashboard.bills")}
                value={sections.purchasing.bill_count}
              />
            </Section>
          )}

          {sections.returns && (
            <Section title={t("dashboard.returns")}>
              <Stat
                icon={RotateCcw}
                label={t("dashboard.awaitingDisposition")}
                tone={sections.returns.pending_disposition_count > 0 ? "warn" : "ink"}
                value={sections.returns.pending_disposition_count}
                sub={t("dashboard.quarantined")}
              />
            </Section>
          )}

          {user?.business_type !== "shop" && sections.crm && (
            <Section title={t("dashboard.crm")}>
              <Stat
                icon={Contact}
                label={t("dashboard.openLeads")}
                value={sections.crm.open_lead_count}
              />
              <Stat
                icon={Wallet}
                label={t("dashboard.pipelineValue")}
                tone="accent"
                value={money(sections.crm.pipeline_value)}
              />
            </Section>
          )}

          {user?.business_type !== "shop" && sections.hr && (
            <Section title={t("dashboard.hr")}>
              <Stat
                icon={UsersRound}
                label={t("dashboard.employees")}
                value={sections.hr.employee_count}
              />
              <Stat
                icon={CalendarClock}
                label={t("dashboard.pendingLeave")}
                tone={sections.hr.pending_leave_count > 0 ? "warn" : "ink"}
                value={sections.hr.pending_leave_count}
                sub={sections.hr.pending_leave_count > 0 ? t("dashboard.awaitingApproval") : undefined}
              />
            </Section>
          )}

          {sections.finance && (
            <Section title={t("dashboard.financeMonth")}>
              <Stat
                icon={Wallet}
                label={t("dashboard.revenueLabel")}
                tone="accent"
                value={money(sections.finance.revenue)}
              />
              <Stat
                icon={TrendingDown}
                label={t("dashboard.expensesLabel")}
                value={money(sections.finance.expenses)}
              />
              {/* Count differences and damage at cost (review 2026-09-24):
                  part of net profit, shown so the net figure adds up. */}
              {Number(sections.finance.stock_adjustments || 0) !== 0 && (
                <Stat
                  icon={TrendingDown}
                  label={t("dashboard.stockAdjustments")}
                  tone={Number(sections.finance.stock_adjustments) > 0 ? "warn" : "ink"}
                  value={money(sections.finance.stock_adjustments)}
                />
              )}
              <Stat
                icon={Scale}
                label={t("improvements.netProfit")}
                tone={Number(sections.finance.net) < 0 ? "warn" : "ink"}
                value={money(sections.finance.net)}
              />
            </Section>
          )}

          {user?.business_type !== "shop" && sections.website && (
            <Section title={t("dashboard.website")}>
              <Stat
                icon={Globe}
                label={t("dashboard.siteStatus")}
                tone={sections.website.is_published ? "ok" : "warn"}
                value={
                  sections.website.is_published
                    ? t("dashboard.published")
                    : t("dashboard.draft")
                }
                sub={
                  sections.website.is_published
                    ? undefined
                    : t("dashboard.publishHint")
                }
              />
              <Stat
                icon={LayoutList}
                label={t("dashboard.pageSections")}
                value={sections.website.section_count}
                sub={
                  sections.website.section_count === 0
                    ? t("dashboard.addSectionsHint")
                    : undefined
                }
              />
            </Section>
          )}

          {Object.keys(sections).length === 0 && (
            <div className="rounded-card border border-line bg-surface p-6 text-muted">
              {t("dashboard.noSections")}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
