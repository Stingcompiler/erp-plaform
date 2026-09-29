"use client";

// Public plan cards, driven by /api/public/plans/. The same component serves
// the landing preview (`compact`) and the pricing page (with the compare
// table under the cards). The last card is the on-server (standalone)
// offer, which is quoted, not priced.
//
// The API rows go through lib/planCatalog.js once (order, one badge, real
// limits/modules first, feature lines deduped, no internal codes); a
// template is only a renderer over those normalized plans — see TEMPLATES.

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Check, Server } from "lucide-react";

import { useI18n } from "../../app/providers/I18nProvider";
import { registration } from "@/lib/api";
import { formatPlanAmount, normalizePlans } from "@/lib/planCatalog";
import { moduleLabel } from "@/lib/planModules";
import ClassicPlanCard from "./pricing/ClassicPlanCard";
import PlanCompareTable from "./pricing/PlanCompareTable";

// One amount and one currency label ("500,000 ج.س"), as on the cards.
export function formatPrice(amount, currency, language) {
  return formatPlanAmount(amount, currency, language);
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

// The API rows as the templates read them, in the UI language.
export function usePlanCatalog(rows) {
  const { t, language } = useI18n();
  return useMemo(
    () => (rows ? normalizePlans(rows, language, {
      module: (code) => moduleLabel(code, t),
      limit: (key) => t(`pricing.limitLabels.${key}`),
    }) : null),
    [rows, language, t],
  );
}

// Card renderers by template name. PR B adds more; each takes
// { plan, compact } with `plan` from normalizePlans().
export const TEMPLATES = { classic: ClassicPlanCard };

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

export default function PlanCards({ compact = false, showCompare = false, template = "classic" }) {
  const { t } = useI18n();
  const { plans: rows, error } = usePublicPlans();
  const plans = usePlanCatalog(rows);
  const Card = TEMPLATES[template] || ClassicPlanCard;

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
        {plans.map((plan) => <Card key={plan.id} plan={plan} compact={compact} />)}
        <StandaloneCard compact={compact} />
      </div>
      {showCompare && <PlanCompareTable plans={plans} />}
    </div>
  );
}
