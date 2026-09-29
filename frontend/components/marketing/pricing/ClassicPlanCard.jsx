"use client";

// The "classic" pricing template: one card per plan. It renders a plan
// normalized by lib/planCatalog.js and holds no pricing rules of its own.

import Link from "next/link";

import { useI18n } from "../../../app/providers/I18nProvider";
import { ExtraRows, LimitRows, ModuleRows, PopularBadge, PriceBlock, TrialBadge } from "./parts";

export default function ClassicPlanCard({ plan, compact = false }) {
  const { t, href } = useI18n();
  const { highlighted } = plan;
  return (
    <article
      className={`relative flex min-w-0 flex-col rounded-card border bg-paper p-6 shadow-card ${
        highlighted ? "border-accent ring-1 ring-accent" : "border-line"
      }`}
    >
      {highlighted && <PopularBadge />}
      <h3 className="break-words font-display text-lg font-semibold">{plan.name}</h3>
      {plan.tagline && <p className="mt-1 text-sm text-muted">{plan.tagline}</p>}
      <PriceBlock plan={plan} />
      <TrialBadge plan={plan} />
      <LimitRows plan={plan} />
      {!compact && <ModuleRows plan={plan} />}
      {!compact && <ExtraRows plan={plan} />}
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
