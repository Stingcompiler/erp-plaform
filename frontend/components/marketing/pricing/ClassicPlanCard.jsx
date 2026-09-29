"use client";

// The "classic" pricing template: one card per plan. It renders a plan
// normalized by lib/planCatalog.js and holds no pricing rules of its own.
// "featured" reuses it with `raised` for the plan in the middle.

import { ExtraRows, LimitRows, ModuleRows, PlanCta, PopularBadge, PriceBlock, TrialBadge } from "./parts";

export default function ClassicPlanCard({ plan, compact = false, raised = false, onSwitchCycle }) {
  const { highlighted } = plan;
  const frame = raised
    ? "border-2 border-accent shadow-xl lg:px-7 lg:py-9"
    : highlighted ? "border border-accent ring-1 ring-accent shadow-card" : "border border-line shadow-card";
  return (
    <article className={`relative flex h-full min-w-0 flex-col rounded-card bg-paper p-6 ${frame} ${plan.available ? "" : "opacity-80"}`}>
      {highlighted && <PopularBadge />}
      <h3 className="break-words font-display text-lg font-semibold">{plan.name}</h3>
      {plan.tagline && <p className="mt-1 text-sm text-muted">{plan.tagline}</p>}
      <PriceBlock plan={plan} />
      {plan.available && <TrialBadge plan={plan} />}
      <LimitRows plan={plan} />
      {!compact && <ModuleRows plan={plan} />}
      {!compact && <ExtraRows plan={plan} />}
      <div className="mt-auto pt-6">
        <PlanCta plan={plan} onSwitchCycle={onSwitchCycle} />
      </div>
    </article>
  );
}
