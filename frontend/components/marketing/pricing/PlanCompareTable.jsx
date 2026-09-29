"use client";

// Modules × plans and limits × plans, generated from the same normalized
// plans as the cards (lib/planCatalog.js compareMatrix), so the table can
// never say something the cards do not. On a phone it scrolls sideways
// inside its own box with the row labels pinned to the reading start.
//
// `primary` is the "table" template: the table IS the pricing section, so
// each plan's column head carries its price and call to action and the
// separate price row goes.

import { Check, Minus, Sparkles } from "lucide-react";

import { useI18n } from "../../../app/providers/I18nProvider";
import { Figure } from "@/components/ui/kit";
import { compareMatrix } from "@/lib/planCatalog";
import { moduleLabel } from "@/lib/planModules";
import { limitValue, periodText, PlanCta, priceText } from "./parts";

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

function PlanHead({ plan, primary, onSwitchCycle, t, language }) {
  const period = periodText(plan, t);
  return (
    <th
      scope="col"
      className={`bg-surface px-3 py-3 text-center align-bottom font-semibold ${plan.highlighted ? "text-accent" : "text-ink"} ${
        primary && plan.highlighted ? "border-t-2 border-accent" : ""
      }`}
    >
      {plan.highlighted && <Sparkles size={14} className="mx-auto mb-1" aria-label={t("pricing.mostPopular")} />}
      <span className="block break-words">{plan.name}</span>
      {primary && (
        <div className="mt-3 font-normal">
          {plan.price.kind === "paid" ? (
            <Figure value={priceText(plan, language, t)} size="price" animate={false} valueClassName="font-bold text-ink" />
          ) : (
            <p className={`font-display font-bold ${plan.price.kind === "unavailable" ? "text-xs text-muted" : "text-lg text-ink"}`}>
              {priceText(plan, language, t)}
            </p>
          )}
          {period && <p className="mt-0.5 text-xs text-muted">{period}</p>}
          <PlanCta plan={plan} onSwitchCycle={onSwitchCycle} size="sm" className="mt-3" />
        </div>
      )}
    </th>
  );
}

export default function PlanCompareTable({ plans, primary = false, onSwitchCycle }) {
  const { t, language } = useI18n();
  if (!plans?.length) return null;
  const { modules, limits } = compareMatrix(plans);
  const cell = "border-t border-line px-3 py-3 text-center";
  // The primary table shares its width equally between the plans, so each
  // price fits its own column (lib/figureFit.js sizes to the column).
  const minWidth = primary ? `${10 + plans.length * 10}rem` : `${11 + plans.length * 8.5}rem`;
  return (
    <section
      className={primary ? "" : "mt-16"}
      aria-labelledby={primary ? undefined : "plans-compare-title"}
      aria-label={primary ? t("pricing.plansCompareTitle") : undefined}
    >
      {!primary && <h2 id="plans-compare-title" className="text-center font-display text-2xl font-bold tracking-tight">{t("pricing.plansCompareTitle")}</h2>}
      {!primary && <p className="mt-2 text-center text-sm text-muted">{t("pricing.plansCompareHint")}</p>}
      {/* Focusable, so a keyboard can scroll it sideways too. */}
      <div
        tabIndex={0}
        role="region"
        aria-label={t("pricing.plansCompareTitle")}
        className={`${primary ? "" : "mt-8"} overflow-x-auto rounded-card border border-line bg-paper shadow-card`}
      >
        <table className={`w-full border-separate border-spacing-0 text-sm ${primary ? "table-fixed" : ""}`} style={{ minWidth }}>
          <thead>
            <tr>
              <th scope="col" className={`${STICKY} ${primary ? "w-36 sm:w-48" : "w-44"} bg-surface px-4 py-3 text-start align-bottom font-medium text-muted`}>
                {t("pricing.feature")}
              </th>
              {plans.map((plan) => (
                <PlanHead key={plan.key ?? plan.id} plan={plan} primary={primary} onSwitchCycle={onSwitchCycle} t={t} language={language} />
              ))}
            </tr>
          </thead>
          <tbody>
            {!primary && (
              <Row label={t("pricing.priceRow")}>
                {plans.map((plan) => (
                  <td key={plan.key ?? plan.id} className={cell}>
                    <span className={`block font-semibold ${plan.price.kind === "unavailable" ? "text-xs text-muted" : "tabular whitespace-nowrap text-ink"}`}>
                      {priceText(plan, language, t)}
                    </span>
                    {periodText(plan, t) && <span className="block text-xs text-muted">{periodText(plan, t)}</span>}
                  </td>
                ))}
              </Row>
            )}
            {modules.length > 0 && <GroupRow label={t("pricing.includedModules")} span={plans.length} />}
            {modules.map((row) => (
              <Row key={row.code} label={moduleLabel(row.code, t)}>
                {row.cells.map((value, index) => <td key={plans[index].key ?? plans[index].id} className={cell}><Mark value={value} t={t} /></td>)}
              </Row>
            ))}
            <Row label={t("pricing.coreModulesRow")}>
              {plans.map((plan) => <td key={plan.key ?? plan.id} className={cell}><Mark value t={t} /></td>)}
            </Row>
            {limits.length > 0 && <GroupRow label={t("pricing.limits")} span={plans.length} />}
            {limits.map((row) => (
              <Row key={row.key} label={t(`pricing.limitLabels.${row.key}`)}>
                {row.cells.map((value, index) => (
                  <td key={plans[index].key ?? plans[index].id} className={`${cell} ${value === null ? "" : "tabular"}`}>{limitValue(row.key, value, t)}</td>
                ))}
              </Row>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
