"use client";

// The pricing page layouts the platform team picks from (/platform-plans →
// "Pricing page layout"). Each one is only a renderer over the same plans
// normalized by lib/planCatalog.js — order, badge, price, limits and
// modules are decided there — so switching layout can never change what a
// plan costs or includes.
//
// A layout takes { plans, compact, onSwitchCycle, selfHosted } and says
// whether it shows the on-server offer itself (`ownsSelfHosted`) or lets
// PlanShowcase put the band under it.

import { useI18n } from "../../../app/providers/I18nProvider";
import { Figure } from "@/components/ui/kit";
import { featuredOrder } from "@/lib/planCatalog";
import ClassicPlanCard from "./ClassicPlanCard";
import PlanCompareTable from "./PlanCompareTable";
import { cardLimitKeys, limitValue, periodText, PlanCta, priceText, StandaloneCard } from "./parts";

// One card per plan in a grid, the on-server card last (the original page).
function ClassicLayout({ plans, compact, onSwitchCycle, selfHosted }) {
  const columns = Math.min(4, Math.max(2, plans.length + (selfHosted ? 1 : 0)));
  const grid = columns >= 4 ? "xl:grid-cols-4" : columns === 3 ? "lg:grid-cols-3" : "";
  return (
    <div className={`grid gap-5 md:grid-cols-2 ${grid}`}>
      {plans.map((plan) => <ClassicPlanCard key={plan.key} plan={plan} compact={compact} onSwitchCycle={onSwitchCycle} />)}
      {selfHosted && <StandaloneCard compact={compact} />}
    </div>
  );
}
ClassicLayout.ownsSelfHosted = true;

// The highlighted plan in the middle, raised, the others flanking it. On a
// phone or tablet (one or two columns) it comes first instead.
function FeaturedLayout({ plans, compact, onSwitchCycle }) {
  const ordered = featuredOrder(plans);
  const hasFeatured = ordered.some((plan) => plan.highlighted);
  return (
    <div className={`flex flex-col gap-5 md:flex-row md:flex-wrap md:justify-center lg:flex-nowrap lg:items-stretch ${hasFeatured ? "lg:py-4" : ""}`}>
      {ordered.map((plan) => (
        <div
          key={plan.key}
          className={`min-w-0 md:w-[calc(50%-0.625rem)] lg:w-auto lg:min-w-0 lg:flex-1 ${
            plan.highlighted ? "order-first lg:order-none lg:z-10 lg:-my-4 lg:flex-[1.15]" : "lg:max-w-sm"
          }`}
        >
          <ClassicPlanCard plan={plan} compact={compact} raised={plan.highlighted} onSwitchCycle={onSwitchCycle} />
        </div>
      ))}
    </div>
  );
}

// The comparison table first: plans as columns, price and call to action
// in each column head, no cards.
function TableLayout({ plans, onSwitchCycle }) {
  return <PlanCompareTable plans={plans} primary onSwitchCycle={onSwitchCycle} />;
}
TableLayout.isTable = true;

// Dense rows — name and tagline, the key limits, price, action — for a
// long price list.
function CompactLayout({ plans, onSwitchCycle }) {
  const { t, language } = useI18n();
  return (
    <ul className="divide-y divide-line overflow-hidden rounded-card border border-line bg-paper shadow-card">
      {plans.map((plan) => {
        const period = periodText(plan, t);
        return (
          <li
            key={plan.key}
            className={`grid min-w-0 gap-3 p-4 sm:p-5 md:grid-cols-[minmax(0,1.2fr)_minmax(0,1.5fr)_minmax(0,1fr)_9rem] md:items-center md:gap-5 ${
              plan.highlighted ? "bg-accent/5" : ""
            } ${plan.available ? "" : "opacity-80"}`}
          >
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="break-words font-display text-base font-semibold">{plan.name}</h3>
                {plan.highlighted && (
                  <span className="rounded-full bg-accent px-2 py-0.5 text-[11px] font-medium text-white">{t("pricing.mostPopular")}</span>
                )}
              </div>
              {plan.tagline && <p className="mt-0.5 text-sm text-muted">{plan.tagline}</p>}
            </div>
            <ul className="flex min-w-0 flex-wrap gap-1.5" aria-label={t("pricing.limits")}>
              {cardLimitKeys(plan).map((key) => (
                <li key={key} className="rounded-control border border-line bg-surface px-2 py-0.5 text-xs">
                  <span className="text-muted">{t(`pricing.limitLabels.${key}`)}</span>{" "}
                  <span className={`font-medium text-ink ${key in plan.limits ? "tabular" : ""}`}>{limitValue(key, plan.limits[key], t)}</span>
                </li>
              ))}
            </ul>
            <div className="min-w-0">
              {plan.price.kind === "paid" ? (
                <Figure value={priceText(plan, language, t)} size="md" animate={false} valueClassName="font-bold text-ink" />
              ) : (
                <p className={`font-display font-bold ${plan.price.kind === "unavailable" ? "text-sm text-muted" : "text-lg text-ink"}`}>{priceText(plan, language, t)}</p>
              )}
              {period && <p className="text-xs text-muted">{period}</p>}
            </div>
            <PlanCta plan={plan} onSwitchCycle={onSwitchCycle} size="sm" />
          </li>
        );
      })}
    </ul>
  );
}

export const TEMPLATES = {
  classic: ClassicLayout,
  featured: FeaturedLayout,
  table: TableLayout,
  compact: CompactLayout,
};
