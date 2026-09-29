"use client";

// Building blocks every pricing template shares. They take a plan already
// normalized by lib/planCatalog.js and only decide how it looks, so a new
// template (PR B) is a new layout of these parts, not new rules.

import Link from "next/link";
import { Check, Server, Sparkles } from "lucide-react";

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
  if (plan.price.kind === "unavailable") return t(`pricing.cycleUnavailable.${plan.cycle}`);
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
      ) : plan.price.kind === "unavailable" ? (
        <p className="text-sm font-medium text-muted">{priceText(plan, language, t)}</p>
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

// The card's call to action. A plan not sold on the cycle the switch is on
// offers to show the cycle it is sold on instead of a sign-up link.
export function PlanCta({ plan, onSwitchCycle, size = "md", className = "" }) {
  const { t, href } = useI18n();
  const pad = size === "sm" ? "px-4 py-2 text-sm" : "px-4 py-3";
  const tone = plan.highlighted
    ? "bg-accent text-white hover:bg-accent-strong"
    : "border border-line bg-surface text-ink hover:border-accent";
  if (!plan.available) {
    const other = plan.offeredCycles[0];
    if (!other || !onSwitchCycle) return null;
    return (
      <button
        type="button"
        onClick={() => onSwitchCycle(other)}
        className={`block w-full rounded-control border border-line bg-surface text-center font-medium text-ink hover:border-accent ${pad} ${className}`}
      >
        {t(`pricing.showCycle.${other}`)}
      </button>
    );
  }
  return (
    <Link href={href(`/register?plan=${plan.id}`)} className={`block rounded-control text-center font-medium ${tone} ${pad} ${className}`}>
      {t("pricing.startTrial")}
    </Link>
  );
}

// Monthly / yearly, only rendered when a plan really has both
// (lib/planCatalog.js billingCycles). It says nothing about savings: the
// prices on the cards are the published ones.
export function CycleToggle({ value, options, onChange }) {
  const { t } = useI18n();
  if (!options?.length) return null;
  return (
    <div className="mb-8 flex justify-center">
      <div role="radiogroup" aria-label={t("pricing.cycleLabel")} className="inline-flex rounded-full border border-line bg-paper p-1 shadow-card">
        {options.map((cycle) => {
          const active = cycle === value;
          return (
            <button
              key={cycle}
              type="button"
              role="radio"
              aria-checked={active}
              onClick={() => onChange(cycle)}
              className={`min-w-24 rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${active ? "bg-accent text-white" : "text-muted hover:text-ink"}`}
            >
              {t(`pricing.cycleNames.${cycle}`)}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function standaloneLines(t) {
  const features = t("pricing.standaloneFeatures");
  return Array.isArray(features) ? features : [];
}

// The on-server (licence) offer, quoted rather than priced: a card beside
// the plan cards (classic) …
export function StandaloneCard({ compact }) {
  const { t, href } = useI18n();
  return (
    <article className="flex min-w-0 flex-col rounded-card border border-line bg-ink p-6 text-paper shadow-card">
      <div className="flex items-center gap-2">
        <span className="grid h-8 w-8 place-items-center rounded-lg bg-white/10"><Server size={18} /></span>
        <h3 className="font-display text-lg font-semibold">{t("pricing.standaloneName")}</h3>
      </div>
      <p className="mt-2 text-sm text-paper/70">{t("pricing.standaloneTagline")}</p>
      <p className="mt-4 font-display text-2xl font-bold">{t("pricing.standalonePrice")}</p>
      <p className="text-sm text-paper/60">{t("pricing.standalonePriceHint")}</p>
      {!compact && (
        <ul className="mt-5 space-y-2 text-sm text-paper/90">
          {standaloneLines(t).map((line) => (
            <li key={line} className="flex items-start gap-2">
              <Check size={16} className="mt-0.5 shrink-0 text-accent" />
              <span>{line}</span>
            </li>
          ))}
        </ul>
      )}
      <div className="mt-auto pt-6">
        <Link href={href("/register?mode=standalone")} className="block rounded-control bg-white/10 px-4 py-3 text-center font-medium text-paper hover:bg-white/20">
          {t("pricing.requestQuote")}
        </Link>
      </div>
    </article>
  );
}

// … or one band under the other layouts, so it never takes the middle of
// "featured" or a column of "table".
export function StandaloneBand() {
  const { t, href } = useI18n();
  return (
    <aside className="mt-8 flex flex-col gap-4 rounded-card border border-line bg-ink p-5 text-paper shadow-card sm:p-6 md:flex-row md:items-center">
      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-white/10"><Server size={20} /></span>
      <div className="min-w-0 flex-1">
        <h3 className="font-display text-lg font-semibold">{t("pricing.standaloneName")}</h3>
        <p className="mt-1 text-sm text-paper/70">{t("pricing.standaloneTagline")}</p>
        <p className="mt-1 text-sm text-paper/60">{t("pricing.standalonePrice")} · {t("pricing.standalonePriceHint")}</p>
      </div>
      <Link href={href("/register?mode=standalone")} className="block shrink-0 rounded-control bg-white/10 px-4 py-3 text-center font-medium text-paper hover:bg-white/20">
        {t("pricing.requestQuote")}
      </Link>
    </aside>
  );
}
