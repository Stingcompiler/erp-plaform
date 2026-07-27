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
  Wallet,
} from "lucide-react";

import { dashboard } from "@/lib/api";
import { useAuth } from "../../providers/AuthProvider";
import { useI18n } from "../../providers/I18nProvider";
import { translateRole } from "@/lib/i18n";
import BarList from "@/components/reports/BarList";

function Stat({ icon: Icon, label, value, tone = "ink", sub }) {
  const toneClass =
    tone === "warn" ? "text-warn" : tone === "accent" ? "text-accent" : "text-ink";
  return (
    <div className="rounded-card border border-line bg-surface p-5 shadow-card">
      <div className="flex items-center gap-2 text-muted">
        <Icon size={16} />
        <span className="text-sm">{label}</span>
      </div>
      <div className={`tabular mt-3 text-3xl font-medium ${toneClass}`}>{value}</div>
      {sub && <div className="mt-1 text-xs text-muted">{sub}</div>}
    </div>
  );
}

function Section({ title, children }) {
  return (
    <section className="mt-8 first:mt-0">
      <h2 className="mb-3 font-display text-sm font-semibold uppercase tracking-wide text-muted">
        {title}
      </h2>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{children}</div>
    </section>
  );
}

export default function DashboardPage() {
  const { user } = useAuth();
  const { t, language } = useI18n();
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);

  const money = (v) =>
    Number(v ?? 0).toLocaleString(language === "ar" ? "ar" : "en", {
      maximumFractionDigits: 2,
    });

  useEffect(() => {
    dashboard
      .get()
      .then((res) => setData(res.data))
      .catch(() => setError(true));
  }, []);

  const sections = data?.sections || {};

  return (
    <div>
      <div className="flex items-baseline justify-between">
        <h1 className="font-display text-2xl font-bold">{t("dashboard.title")}</h1>
        <span className="text-sm text-muted">{translateRole(user?.role_name, t)}</span>
      </div>

      {error && (
        <div className="mt-6 rounded-card border border-line bg-surface p-6 text-muted">
          {t("dashboard.loadError")}
        </div>
      )}

      {!data && !error && <div className="mt-6 text-muted">{t("common.loading")}</div>}

      {data && (
        <div className="mt-6">
          {sections.sales && (
            <Section title={t("dashboard.sales")}>
              <Stat
                icon={Receipt}
                label={t("dashboard.invoices")}
                value={sections.sales.invoice_count}
              />
              <Stat
                icon={Wallet}
                label={t("dashboard.revenue")}
                tone="accent"
                value={money(sections.sales.revenue_total)}
              />
            </Section>
          )}

          {/* Chart — top products by revenue, scoped to the same company/branch
              as the sales totals above. */}
          {sections.sales?.top_products?.length > 0 && (
            <section className="mt-8">
              <h2 className="mb-3 font-display text-sm font-semibold uppercase tracking-wide text-muted">
                {t("reports.topProducts")}
              </h2>
              <div className="rounded-card border border-line bg-surface p-5 shadow-card">
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

          {sections.crm && (
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

          {sections.hr && (
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
            <Section title={t("dashboard.finance")}>
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
              <Stat
                icon={Scale}
                label={t("dashboard.net")}
                tone={Number(sections.finance.net) < 0 ? "warn" : "ink"}
                value={money(sections.finance.net)}
              />
            </Section>
          )}

          {sections.website && (
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
