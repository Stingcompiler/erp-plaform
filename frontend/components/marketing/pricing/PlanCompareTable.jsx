"use client";

// Modules × plans and limits × plans, generated from the same normalized
// plans as the cards (lib/planCatalog.js compareMatrix), so the table can
// never say something the cards do not. On a phone it scrolls sideways
// inside its own box with the row labels pinned to the reading start.

import { Check, Minus, Sparkles } from "lucide-react";

import { useI18n } from "../../../app/providers/I18nProvider";
import { compareMatrix } from "@/lib/planCatalog";
import { moduleLabel } from "@/lib/planModules";
import { limitValue, periodText, priceText } from "./parts";

const STICKY = "sticky start-0 z-10 border-e border-line";

function Mark({ value, t }) {
  return value
    ? <Check size={18} className="mx-auto text-accent" aria-label={t("pricing.included")} />
    : <Minus size={18} className="mx-auto text-muted" aria-label={t("pricing.notIncluded")} />;
}

function GroupRow({ label, span }) {
  return (
    <tr>
      <th scope="rowgroup" className={`${STICKY} bg-surface px-4 pb-2 pt-5 text-start text-xs font-semibold uppercase tracking-wide text-muted`}>{label}</th>
      <td colSpan={span} className="bg-surface" />
    </tr>
  );
}

function Row({ label, children }) {
  return (
    <tr>
      <th scope="row" className={`${STICKY} border-t bg-paper px-4 py-3 text-start font-normal`}>{label}</th>
      {children}
    </tr>
  );
}

export default function PlanCompareTable({ plans }) {
  const { t, language } = useI18n();
  if (!plans?.length) return null;
  const { modules, limits } = compareMatrix(plans);
  const cell = "border-t border-line px-3 py-3 text-center";
  return (
    <section className="mt-16" aria-labelledby="plans-compare-title">
      <h2 id="plans-compare-title" className="text-center font-display text-2xl font-bold tracking-tight">{t("pricing.plansCompareTitle")}</h2>
      <p className="mt-2 text-center text-sm text-muted">{t("pricing.plansCompareHint")}</p>
      {/* Focusable, so a keyboard can scroll it sideways too. */}
      <div tabIndex={0} role="region" aria-label={t("pricing.plansCompareTitle")} className="mt-8 overflow-x-auto rounded-card border border-line bg-paper shadow-card">
        <table className="w-full border-separate border-spacing-0 text-sm" style={{ minWidth: `${11 + plans.length * 8.5}rem` }}>
          <thead>
            <tr>
              <th scope="col" className={`${STICKY} w-44 bg-surface px-4 py-3 text-start font-medium text-muted`}>{t("pricing.feature")}</th>
              {plans.map((plan) => (
                <th key={plan.id} scope="col" className={`bg-surface px-3 py-3 text-center align-bottom font-semibold ${plan.highlighted ? "text-accent" : "text-ink"}`}>
                  {plan.highlighted && <Sparkles size={14} className="mx-auto mb-1" aria-label={t("pricing.mostPopular")} />}
                  <span className="break-words">{plan.name}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <Row label={t("pricing.priceRow")}>
              {plans.map((plan) => (
                <td key={plan.id} className={cell}>
                  <span className="tabular block whitespace-nowrap font-semibold text-ink">{priceText(plan, language, t)}</span>
                  {periodText(plan, t) && <span className="block text-xs text-muted">{periodText(plan, t)}</span>}
                </td>
              ))}
            </Row>
            {modules.length > 0 && <GroupRow label={t("pricing.includedModules")} span={plans.length} />}
            {modules.map((row) => (
              <Row key={row.code} label={moduleLabel(row.code, t)}>
                {row.cells.map((value, index) => <td key={plans[index].id} className={cell}><Mark value={value} t={t} /></td>)}
              </Row>
            ))}
            <Row label={t("pricing.coreModulesRow")}>
              {plans.map((plan) => <td key={plan.id} className={cell}><Mark value t={t} /></td>)}
            </Row>
            {limits.length > 0 && <GroupRow label={t("pricing.limits")} span={plans.length} />}
            {limits.map((row) => (
              <Row key={row.key} label={t(`pricing.limitLabels.${row.key}`)}>
                {row.cells.map((value, index) => <td key={plans[index].id} className={`${cell} ${value === null ? "" : "tabular"}`}>{limitValue(row.key, value, t)}</td>)}
              </Row>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
