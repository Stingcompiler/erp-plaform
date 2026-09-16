"use client";

// Public plan cards, driven by /api/public/plans/. The same component serves
// the landing preview (`compact`) and the pricing page. The last card is the
// on-server (standalone) offer, which is quoted, not priced.

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Check, Server, Sparkles } from "lucide-react";

import { useI18n } from "../../app/providers/I18nProvider";
import { registration } from "@/lib/api";
import { expandModules, moduleLabel } from "@/lib/planModules";

export function formatPrice(amount, currency, language) {
  const value = Number(amount);
  const locale = language === "ar" ? "ar-EG-u-nu-latn" : "en-US";
  try {
    return new Intl.NumberFormat(locale, {
      style: "currency",
      currency,
      minimumFractionDigits: 0,
      maximumFractionDigits: Number.isInteger(value) ? 0 : 2,
    }).format(value);
  } catch {
    // An unknown ISO code (an operator typo) must not blank the card.
    return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 2 }).format(value)} ${currency}`;
  }
}

export function usePublicPlans() {
  const [plans, setPlans] = useState(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    let cancelled = false;
    registration
      .publicPlans()
      .then((response) => { if (!cancelled) setPlans(response.data || []); })
      .catch(() => { if (!cancelled) { setPlans([]); setError(true); } });
    return () => { cancelled = true; };
  }, []);
  return { plans, error };
}

function LimitLine({ plan }) {
  const { t } = useI18n();
  const limits = plan.limits || {};
  const parts = [
    ["users", "pricing.limitUsers"],
    ["branches", "pricing.limitBranches"],
    ["warehouses", "pricing.limitWarehouses"],
  ]
    // A key that is absent from the plan is uncapped (see assert_capacity);
    // only real caps are shown.
    .filter(([key]) => key in limits)
    .map(([key, labelKey]) => t(labelKey, { count: limits[key] }));
  if (!parts.length) return null;
  return <p className="mt-3 text-sm text-muted">{parts.join(" · ")}</p>;
}

// Every module the version includes, "*" expanded to the full list, so the
// visitor sees what they get rather than a code.
function ModuleChips({ modules }) {
  const { t } = useI18n();
  const labels = useMemo(() => expandModules(modules).map((code) => moduleLabel(code, t)), [modules, t]);
  if (!labels.length) return null;
  return (
    <div className="mt-4 flex flex-wrap gap-1.5">
      {labels.map((label) => (
        <span key={label} className="rounded-full border border-line bg-surface px-2.5 py-1 text-xs text-muted">{label}</span>
      ))}
    </div>
  );
}

function HostedCard({ plan, compact }) {
  const { t, language, href } = useI18n();
  const display = plan.display || {};
  const name = display.name?.[language] || plan.plan_name;
  const tagline = display.tagline?.[language] || "";
  const features = display.features?.[language]?.length ? display.features[language] : display.features?.en || [];
  const highlighted = Boolean(display.is_highlighted);
  const cycle = plan.billing_cycle === "yearly" ? t("pricing.perYear") : t("pricing.perMonth");
  return (
    <article
      className={`relative flex flex-col rounded-card border bg-paper p-6 shadow-card ${
        highlighted ? "border-accent ring-1 ring-accent" : "border-line"
      }`}
    >
      {highlighted && (
        <span className="absolute -top-3 start-6 inline-flex items-center gap-1 rounded-full bg-accent px-3 py-1 text-xs font-medium text-white">
          <Sparkles size={12} /> {t("pricing.mostPopular")}
        </span>
      )}
      <h3 className="font-display text-lg font-semibold">{name}</h3>
      {tagline && <p className="mt-1 text-sm text-muted">{tagline}</p>}
      <p className="mt-4 flex items-baseline gap-1">
        <span className="tabular font-display text-3xl font-bold text-ink">{formatPrice(plan.price, plan.currency, language)}</span>
        <span className="text-sm text-muted">{cycle}</span>
      </p>
      {plan.trial_days > 0 && (
        <span className="mt-3 inline-block w-fit rounded-control bg-accent/10 px-2.5 py-1 text-xs font-medium text-accent">
          {t("pricing.trialBadge", { days: plan.trial_days })}
        </span>
      )}
      <LimitLine plan={plan} />
      {!compact && features.length > 0 && (
        <ul className="mt-5 space-y-2 text-sm">
          {features.map((line) => (
            <li key={line} className="flex items-start gap-2">
              <Check size={16} className="mt-0.5 shrink-0 text-accent" />
              <span>{line}</span>
            </li>
          ))}
        </ul>
      )}
      {!compact && <ModuleChips modules={plan.modules} />}
      <div className="mt-auto pt-6">
        <Link
          href={href(`/register?plan=${plan.id}`)}
          className={`block rounded-control px-4 py-3 text-center font-medium ${
            highlighted ? "bg-accent text-white hover:bg-accent-strong" : "border border-line bg-surface text-ink hover:border-accent"
          }`}
        >
          {t("pricing.startTrial")}
        </Link>
      </div>
    </article>
  );
}

function StandaloneCard({ compact }) {
  const { t, href } = useI18n();
  const features = t("pricing.standaloneFeatures");
  return (
    <article className="flex flex-col rounded-card border border-line bg-ink p-6 text-paper shadow-card">
      <div className="flex items-center gap-2">
        <span className="grid h-8 w-8 place-items-center rounded-lg bg-white/10"><Server size={18} /></span>
        <h3 className="font-display text-lg font-semibold">{t("pricing.standaloneName")}</h3>
      </div>
      <p className="mt-2 text-sm text-paper/70">{t("pricing.standaloneTagline")}</p>
      <p className="mt-4 font-display text-2xl font-bold">{t("pricing.standalonePrice")}</p>
      <p className="text-sm text-paper/60">{t("pricing.standalonePriceHint")}</p>
      {!compact && Array.isArray(features) && (
        <ul className="mt-5 space-y-2 text-sm text-paper/90">
          {features.map((line) => (
            <li key={line} className="flex items-start gap-2">
              <Check size={16} className="mt-0.5 shrink-0 text-accent" />
              <span>{line}</span>
            </li>
          ))}
        </ul>
      )}
      <div className="mt-auto pt-6">
        <Link
          href={href("/register?mode=standalone")}
          className="block rounded-control bg-white/10 px-4 py-3 text-center font-medium text-paper hover:bg-white/20"
        >
          {t("pricing.requestQuote")}
        </Link>
      </div>
    </article>
  );
}

export default function PlanCards({ compact = false }) {
  const { t } = useI18n();
  const { plans, error } = usePublicPlans();

  if (plans === null) {
    return (
      <div className="grid gap-5 md:grid-cols-3" aria-busy="true">
        {[0, 1, 2].map((i) => <div key={i} className="h-64 animate-pulse rounded-card border border-line bg-paper" />)}
      </div>
    );
  }
  const columns = Math.min(4, Math.max(2, plans.length + 1));
  return (
    <div>
      {error && <p className="mb-4 text-center text-sm text-danger">{t("pricing.loadError")}</p>}
      {!error && plans.length === 0 && <p className="mb-4 text-center text-muted">{t("pricing.quoteOnly")}</p>}
      <div className={`grid gap-5 md:grid-cols-2 ${columns >= 4 ? "xl:grid-cols-4" : columns === 3 ? "lg:grid-cols-3" : ""}`}>
        {plans.map((plan) => <HostedCard key={plan.id} plan={plan} compact={compact} />)}
        <StandaloneCard compact={compact} />
      </div>
    </div>
  );
}
