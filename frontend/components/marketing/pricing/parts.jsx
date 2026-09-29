"use client";

// Building blocks every pricing template shares. They take a plan already
// normalized by lib/planCatalog.js and only decide how it looks, so a new
// template (PR B) is a new layout of these parts, not new rules.

import { Check, Sparkles } from "lucide-react";

import { useI18n } from "../../../app/providers/I18nProvider";
import { Figure } from "@/components/ui/kit";
import { COUNTED_LIMITS, formatPlanAmount } from "@/lib/planCatalog";
import { moduleLabel } from "@/lib/planModules";

// "4", "Unlimited", "5 GB": one limit's value in the reader's words. A
// limit the version leaves out is uncapped (the server enforces only the
// keys it sets).
export function limitValue(key, value, t) {
  if (value === null || value === undefined) return t("pricing.unlimited");
  if (key === "storage_mb") {
    const gb = Math.round((Number(value) / 1024) * 10) / 10;
    return t("pricing.storageValue", { value: gb });
  }
  return String(value);
}

// The limits a card lists: the counted ones always (so "unlimited" is said,
// not implied), storage only when the version prices it.
export function cardLimitKeys(plan) {
  return [...COUNTED_LIMITS, ...("storage_mb" in plan.limits ? ["storage_mb"] : [])];
}

export function priceText(plan, language, t) {
  if (plan.price.kind === "free") return t("pricing.free");
  if (plan.price.kind === "custom") return t("pricing.customPrice");
  return formatPlanAmount(plan.price.amount, plan.price.currency, language);
}

export function periodText(plan, t) {
  if (plan.price.kind !== "paid") return "";
  return plan.cycle === "yearly" ? t("pricing.perYearLine") : t("pricing.perMonthLine");
}

// The amount on one line, shrunk to the card's width rather than wrapped
// (lib/figureFit.js), one currency label, and the period on its own line.
export function PriceBlock({ plan, inverse = false }) {
  const { t, language } = useI18n();
  const period = periodText(plan, t);
  return (
    <div className="mt-5">
      {plan.price.kind === "paid" ? (
        <Figure
          value={priceText(plan, language, t)}
          size="price"
          animate={false}
          valueClassName={`font-bold ${inverse ? "text-paper" : "text-ink"}`}
        />
      ) : (
        <p className={`font-display text-2xl font-bold sm:text-3xl ${inverse ? "text-paper" : "text-ink"}`}>{priceText(plan, language, t)}</p>
      )}
      {period && <p className="mt-1 text-sm text-muted">{period}</p>}
    </div>
  );
}

export function PopularBadge() {
  const { t } = useI18n();
  return (
    <span className="absolute -top-3 start-6 inline-flex items-center gap-1 rounded-full bg-accent px-3 py-1 text-xs font-medium text-white">
      <Sparkles size={12} aria-hidden="true" /> {t("pricing.mostPopular")}
    </span>
  );
}

export function TrialBadge({ plan }) {
  const { t } = useI18n();
  if (!plan.trialDays) return null;
  return (
    <span className="mt-3 inline-block w-fit rounded-control bg-accent/10 px-2.5 py-1 text-xs font-medium text-accent">
      {t("pricing.trialBadge", { days: plan.trialDays })}
    </span>
  );
}

// Labelled capacity rows: "Users … 4".
export function LimitRows({ plan }) {
  const { t } = useI18n();
  return (
    <div className="mt-5">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-muted">{t("pricing.limits")}</h4>
      <dl className="mt-2 divide-y divide-line rounded-control border border-line text-sm">
        {cardLimitKeys(plan).map((key) => (
          <div key={key} className="flex items-center justify-between gap-3 px-3 py-2">
            <dt className="text-muted">{t(`pricing.limitLabels.${key}`)}</dt>
            <dd className={`font-medium text-ink ${key in plan.limits ? "tabular" : ""}`}>{limitValue(key, plan.limits[key], t)}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function CheckRow({ children, muted = false }) {
  return (
    <li className={`flex items-start gap-2 ${muted ? "text-muted" : ""}`}>
      <Check size={16} className="mt-0.5 shrink-0 text-accent" aria-hidden="true" />
      <span className="min-w-0">{children}</span>
    </li>
  );
}

// The modules the version includes, in the app's words, then the core
// modules every plan has as one line.
export function ModuleRows({ plan }) {
  const { t } = useI18n();
  return (
    <div className="mt-5">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-muted">{t("pricing.includedModules")}</h4>
      {plan.allModules && <p className="mt-1 text-xs text-accent">{t("pricing.allModulesNote")}</p>}
      <ul className="mt-2 space-y-1.5 text-sm">
        {plan.modules.map((code) => <CheckRow key={code}>{moduleLabel(code, t)}</CheckRow>)}
        <CheckRow muted>{t("pricing.coreModulesRow")}</CheckRow>
      </ul>
    </div>
  );
}

// Marketing lines left after the real data (lib/planCatalog.js extraFeatures).
export function ExtraRows({ plan }) {
  const { t } = useI18n();
  if (!plan.extras.length) return null;
  return (
    <div className="mt-5">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-muted">{t("pricing.extrasTitle")}</h4>
      <ul className="mt-2 space-y-1.5 text-sm">
        {plan.extras.map((line) => <CheckRow key={line}>{line}</CheckRow>)}
      </ul>
    </div>
  );
}
