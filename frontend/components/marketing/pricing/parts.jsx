"use client";

// Building blocks every pricing template shares. They take a plan already
// normalized by lib/planCatalog.js and only decide how it looks, so a new
// template is a new layout of these parts, not new rules.

import { useId, useState } from "react";
import Link from "next/link";
import { Check, ChevronDown, Server, Sparkles } from "lucide-react";

import { useI18n } from "../../../app/providers/I18nProvider";
import { Figure } from "@/components/ui/kit";
import { COUNTED_LIMITS, formatPlanAmount } from "@/lib/planCatalog";
import { moduleLabel } from "@/lib/planModules";
import { sharedFigureChars } from "@/lib/planDeck";
import { useMediaQuery } from "@/lib/useMediaQuery";

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

// One --figure-chars for every paid price in a set of cards, so they all
// render at the size the longest one fits (lib/planDeck.js).
export function usePriceChars(plans) {
  const { t, language } = useI18n();
  return sharedFigureChars((plans || []).filter((plan) => plan.price.kind === "paid").map((plan) => priceText(plan, language, t)));
}

// The amount on one line at the shared size (`chars`), one currency label.
// Free / on request / not on this cycle read as words.
export function PriceFigure({ plan, chars, size = "price", inverse = false }) {
  const { t, language } = useI18n();
  if (plan.price.kind === "paid") {
    return (
      <Figure
        value={priceText(plan, language, t)}
        size={size}
        chars={chars}
        animate={false}
        valueClassName={`font-bold ${inverse ? "text-paper" : "text-ink"}`}
      />
    );
  }
  if (plan.price.kind === "unavailable") return <p className="text-sm font-medium text-muted">{priceText(plan, language, t)}</p>;
  return <p className={`font-display text-2xl font-bold sm:text-3xl ${inverse ? "text-paper" : "text-ink"}`}>{priceText(plan, language, t)}</p>;
}

// "Most popular", inside the card's top row (never across its border).
export function PopularBadge({ className = "" }) {
  const { t } = useI18n();
  return (
    <span className={`inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full bg-accent px-2.5 py-1 text-xs font-medium text-white ${className}`}>
      <Sparkles size={12} aria-hidden="true" /> {t("pricing.mostPopular")}
    </span>
  );
}

export function TrialBadge({ plan }) {
  const { t } = useI18n();
  if (!plan.trialDays || !plan.available) return null;
  return (
    // accent-strong, not accent: 12 px text on accent/10 needs 4.5:1, and the
    // light accent measured 4.09:1 there (landing review 2026-09-29).
    <span className="inline-block w-fit rounded-control bg-accent/10 px-2.5 py-0.5 text-xs font-medium text-accent-strong">
      {t("pricing.trialBadge", { days: plan.trialDays })}
    </span>
  );
}

// The capacity as stat tiles, two by two: the value large, its label under.
export function LimitTiles({ plan }) {
  const { t } = useI18n();
  const keys = cardLimitKeys(plan);
  return (
    <dl className="grid grid-cols-2 gap-2" aria-label={t("pricing.limits")}>
      {keys.map((key, index) => (
        <div
          key={key}
          className={`flex min-w-0 flex-col-reverse rounded-control border border-line bg-surface px-3 py-1 ${
            index === keys.length - 1 && keys.length % 2 ? "col-span-2" : ""
          }`}
        >
          <dt className="truncate text-[11px] leading-4 text-muted">{t(`pricing.limitLabels.${key}`)}</dt>
          <dd className={`font-display text-base font-semibold leading-5 text-ink ${key in plan.limits ? "tabular" : ""}`}>
            {limitValue(key, plan.limits[key], t)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function CheckRow({ children, muted = false, className = "" }) {
  return (
    <li className={`flex items-start gap-2 ${muted ? "text-muted" : ""} ${className}`}>
      <Check size={16} className="mt-0.5 shrink-0 text-accent" aria-hidden="true" />
      <span className="min-w-0">{children}</span>
    </li>
  );
}

function modulesSummary(count, t, language) {
  let category = "other";
  try { category = new Intl.PluralRules(language).select(count); } catch { /* old engine */ }
  const text = t(`pricing.modulesSummary.${category}`, { count });
  return text.startsWith("pricing.") ? t("pricing.modulesSummary.other", { count }) : text;
}

// "Includes 5 modules" — the modules in the app's words behind a
// disclosure: closed on phones and tablets (the card stays short), open
// from 1024px. The visitor's own toggle wins after that.
export function ModulesDisclosure({ plan }) {
  const { t, language } = useI18n();
  const wide = useMediaQuery("(min-width: 1024px)");
  const [choice, setChoice] = useState(null);
  const open = choice ?? wide;
  const panel = useId();
  return (
    <div className="border-t border-line pt-2">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panel}
        onClick={() => setChoice(!open)}
        className="flex w-full items-center justify-between gap-2 rounded-control py-1 text-start text-sm font-semibold text-ink hover:text-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
      >
        <span>{modulesSummary(plan.modules.length, t, language)}</span>
        <ChevronDown size={16} aria-hidden="true" className={`shrink-0 text-muted transition-transform motion-reduce:transition-none ${open ? "rotate-180" : ""}`} />
      </button>
      <div id={panel} hidden={!open} className="pt-2">
        {plan.allModules && <p className="mb-2 text-xs text-accent">{t("pricing.allModulesNote")}</p>}
        {/* Chips: they pack densely at any card width without breaking a
            module's name over two lines. */}
        <ul className="flex flex-wrap gap-1.5">
          {plan.modules.map((code) => (
            <li key={code} className="inline-flex items-center gap-1 rounded-full border border-line bg-surface px-2 py-0.5 text-xs text-ink">
              <Check size={12} className="shrink-0 text-accent" aria-hidden="true" />
              {moduleLabel(code, t)}
            </li>
          ))}
        </ul>
        <p className="mt-2 text-xs text-muted">{t("pricing.coreModulesRow")}</p>
      </div>
    </div>
  );
}

// Marketing lines left after the real data (lib/planCatalog.js
// extraFeatures): four at most (three on a phone, where the card has to
// stay short), the rest behind "+N more".
export const EXTRAS_SHOWN = 4;
export const EXTRAS_SHOWN_PHONE = 3;
export function ExtrasList({ plan }) {
  const { t } = useI18n();
  const [all, setAll] = useState(false);
  const list = useId();
  const shown = useMediaQuery("(min-width: 640px)") ? EXTRAS_SHOWN : EXTRAS_SHOWN_PHONE;
  if (!plan.extras.length) return null;
  const hidden = plan.extras.length - shown;
  const lines = all || hidden <= 0 ? plan.extras : plan.extras.slice(0, shown);
  return (
    <div>
      {/* The title and the "+N more" toggle share one line. */}
      <div className="flex items-center justify-between gap-3">
        <h4 className="text-xs font-semibold text-muted">{t("pricing.extrasTitle")}</h4>
        {hidden > 0 && (
          <button
            type="button"
            aria-expanded={all}
            aria-controls={list}
            onClick={() => setAll(!all)}
            className="shrink-0 rounded-control text-xs font-medium text-accent hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
          >
            {all ? t("pricing.fewerExtras") : t("pricing.moreExtras", { count: hidden })}
          </button>
        )}
      </div>
      <ul id={list} className="mt-1.5 space-y-1 text-[0.8125rem] leading-[1.125rem] sm:text-sm">
        {lines.map((line) => <CheckRow key={line}>{line}</CheckRow>)}
      </ul>
    </div>
  );
}

// The card's call to action. A plan not sold on the cycle the switch is on
// offers to show the cycle it is sold on instead of a sign-up link.
export function PlanCta({ plan, onSwitchCycle, size = "md", className = "" }) {
  const { t, href } = useI18n();
  const pad = size === "sm" ? "px-4 py-2 text-sm" : "px-4 py-2.5";
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

// The on-server (licence) offer's key points: four at most on the band.
const STANDALONE_POINTS = 4;
function standaloneLines(t) {
  const features = t("pricing.standaloneFeatures");
  return Array.isArray(features) ? features.slice(0, STANDALONE_POINTS) : [];
}

// The on-server (licence) offer, quoted rather than priced: one full-width
// band under the plans in every layout, never a plan column. Stacked on a
// phone; icon + copy | key points in two columns | quote button from 1024.
// Keeps the dark "inverse" panel of the design system.
export function StandaloneBand({ compact = false }) {
  const { t, href } = useI18n();
  const points = compact ? [] : standaloneLines(t);
  return (
    <aside
      aria-labelledby="standalone-offer"
      className="plan-band mt-8 grid gap-4 rounded-card border border-line bg-ink p-5 text-paper shadow-card sm:p-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)_auto] lg:items-center lg:gap-8"
    >
      <div className="min-w-0">
        <div className="flex items-center gap-3">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-paper/10"><Server size={20} aria-hidden="true" /></span>
          <h3 id="standalone-offer" className="font-display text-lg font-semibold">{t("pricing.standaloneName")}</h3>
        </div>
        <p className="mt-2 text-sm text-paper/70">{t("pricing.standaloneTagline")}</p>
        <p className="mt-1 text-sm text-paper/60">{t("pricing.standalonePrice")} · {t("pricing.standalonePriceHint")}</p>
      </div>
      {points.length > 0 ? (
        <ul className="grid gap-x-6 gap-y-2 text-sm text-paper/90 md:grid-cols-2">
          {points.map((line) => (
            <li key={line} className="flex items-start gap-2">
              <Check size={16} className="mt-0.5 shrink-0 text-pro-inverse" aria-hidden="true" />
              <span className="min-w-0">{line}</span>
            </li>
          ))}
        </ul>
      ) : <div className="hidden lg:block" />}
      <Link
        href={href("/register?mode=standalone")}
        className="block rounded-control bg-paper/10 px-5 py-3 text-center font-medium text-paper ring-1 ring-paper/15 hover:bg-paper/20 sm:justify-self-start lg:justify-self-auto"
      >
        {t("pricing.requestQuote")}
      </Link>
    </aside>
  );
}
