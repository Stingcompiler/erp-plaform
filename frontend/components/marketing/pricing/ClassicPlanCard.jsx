"use client";

// One plan card ("classic" and "featured" share it). It renders a plan
// normalized by lib/planCatalog.js and holds no pricing rules of its own.
//
// Seven rows, top to bottom, always in this order and always present (an
// empty one is empty), because from 1024px the cards are CSS subgrids of
// PlanDeck's grid (.plan-card in globals.css): each row lines up with the
// same row of the cards beside it — names, prices, buttons, limit tiles.
//
//   1 name + tagline, the badge in the same row   5 limits, 2×2 stat tiles
//   2 price, one size for every card ("chars")    6 "Includes N modules"
//   3 period + trial chip                         7 extras, 4 + "+N more"
//   4 the call to action, right under the price

import { useI18n } from "../../../app/providers/I18nProvider";
import { ExtrasList, LimitTiles, ModulesDisclosure, periodText, PlanCta, PopularBadge, PriceFigure, TrialBadge } from "./parts";

export default function ClassicPlanCard({ plan, chars, compact = false, raised = false, onSwitchCycle, index, id }) {
  const { t } = useI18n();
  const { highlighted } = plan;
  const period = periodText(plan, t);
  // A ring (box-shadow) rather than a thicker border: emphasis without
  // moving anything by a pixel.
  const frame = highlighted
    ? `plan-card--highlighted border-accent ring-accent ${raised ? "ring-2 shadow-xl" : "ring-1 shadow-lg"}`
    : "border-line shadow-card";
  return (
    <article
      id={id}
      data-index={index}
      aria-label={plan.name}
      className={`plan-card relative min-w-0 rounded-card border bg-paper p-4 sm:p-5 lg:p-6 ${frame} ${plan.available ? "" : "opacity-80"}`}
    >
      <header className="min-w-0">
        <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
          <h3 className="min-w-0 break-words font-display text-lg font-semibold">{plan.name}</h3>
          {highlighted && <PopularBadge />}
        </div>
        {plan.tagline && <p className="mt-0.5 text-sm text-muted">{plan.tagline}</p>}
      </header>
      <div className="mt-3 min-w-0">
        <PriceFigure plan={plan} chars={chars} />
      </div>
      <div className="mt-1 flex min-h-6 flex-wrap items-center gap-x-3 gap-y-1">
        {period && <span className="text-sm text-muted">{period}</span>}
        <TrialBadge plan={plan} />
      </div>
      <div className="mt-3">
        <PlanCta plan={plan} onSwitchCycle={onSwitchCycle} />
      </div>
      <div className="mt-3">
        <LimitTiles plan={plan} />
      </div>
      <div className={compact ? "" : "mt-3"}>
        {!compact && <ModulesDisclosure plan={plan} />}
      </div>
      <div className={compact || !plan.extras.length ? "" : "mt-3"}>
        {!compact && <ExtrasList plan={plan} />}
      </div>
    </article>
  );
}
