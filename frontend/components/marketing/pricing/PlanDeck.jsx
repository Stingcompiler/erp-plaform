"use client";

// How the plan cards are laid out at each width (the CSS is .plan-deck in
// globals.css; the rules are lib/planDeck.js):
//
//   < 640     a scroll-snap carousel, one card (86% wide) centred with the
//             next one peeking, plan pills above it that follow the scroll;
//   640–1023  the same carousel two cards at a time — or, with two plans
//             or fewer, a plain two-column grid;
//   ≥ 1024    a centred grid of plan columns (at most 380px each), the
//             cards' rows aligned across the grid with subgrid.
//
// The on-server offer is never a card here: PlanShowcase puts it under the
// deck as a band.
//
// The carousel scrolls inside its own box (the page never scrolls
// sideways), in either direction: a pill tap scrolls by the distance
// between two viewport rects, never by a scrollLeft value, whose sign
// differs between RTL implementations.

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import { useI18n } from "../../../app/providers/I18nProvider";
import { carouselAt, deckColumns, pickActiveIndex, scrollDelta } from "@/lib/planDeck";
import { prefersReducedMotion } from "@/lib/useReducedMotionSafe";
import ClassicPlanCard from "./ClassicPlanCard";
import { usePriceChars } from "./parts";

const useIsoLayoutEffect = typeof window === "undefined" ? useEffect : useLayoutEffect;

// The deck's frame: the same classes for the real cards and the skeleton,
// so both take the same shape at every width.
export function deckClasses(count, bleed = true) {
  const carousel = carouselAt(count);
  return [
    "plan-deck",
    bleed ? "" : "plan-deck--flush",
    carousel.tablet ? "" : "plan-deck--pair",
  ].filter(Boolean).join(" ");
}

export function deckStyle(count) {
  const columns = deckColumns(count);
  return { "--deck-count": Math.max(1, count), "--deck-cols-lg": columns.lg, "--deck-cols-xl": columns.xl };
}

function scrollToCard(track, card, instant = false) {
  if (!track || !card) return;
  const style = getComputedStyle(track);
  const align = getComputedStyle(card).scrollSnapAlign.split(" ").pop();
  const delta = scrollDelta({
    card: card.getBoundingClientRect(),
    track: track.getBoundingClientRect(),
    align: align === "start" || align === "end" ? align : "center",
    rtl: style.direction === "rtl",
    inset: parseFloat(style.scrollPaddingInlineStart) || 0,
  });
  if (Math.abs(delta) < 1) return;
  track.scrollBy({ left: delta, behavior: instant || prefersReducedMotion() ? "instant" : "smooth" });
}

export default function PlanDeck({ plans, compact = false, raised = false, onSwitchCycle, bleed = true }) {
  const { t } = useI18n();
  const chars = usePriceChars(plans);
  const trackRef = useRef(null);
  const pillsRef = useRef(null);
  const preferred = useRef(null);
  const highlightedIndex = Math.max(0, plans.findIndex((plan) => plan.highlighted));
  const [active, setActive] = useState(highlightedIndex);
  const count = plans.length;
  const keys = plans.map((plan) => plan.key).join(",");

  const cards = useCallback(() => [...(trackRef.current?.querySelectorAll(":scope > .plan-card") || [])], []);

  // The highlighted plan starts in view (centred on a phone), before the
  // first paint, so nothing visibly jumps.
  useIsoLayoutEffect(() => {
    const track = trackRef.current;
    if (!track || highlightedIndex === 0 || track.scrollWidth <= track.clientWidth) return;
    preferred.current = highlightedIndex;
    scrollToCard(track, cards()[highlightedIndex], true);
    // Only on mount / a new set of plans.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [keys]);

  // The pills follow the most visible card.
  useEffect(() => {
    const track = trackRef.current;
    if (!track || typeof IntersectionObserver === "undefined") return undefined;
    const list = cards();
    const ratios = list.map(() => 0);
    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        const index = list.indexOf(entry.target);
        if (index >= 0) ratios[index] = entry.intersectionRatio;
      }
      setActive(pickActiveIndex(ratios, preferred.current));
    }, { root: track, threshold: [0, 0.25, 0.5, 0.75, 0.9, 1] });
    list.forEach((card) => observer.observe(card));
    // A swipe, wheel or key in the track is the visitor's own choice.
    const forget = () => { preferred.current = null; };
    track.addEventListener("pointerdown", forget);
    track.addEventListener("wheel", forget, { passive: true });
    track.addEventListener("keydown", forget);
    return () => {
      observer.disconnect();
      track.removeEventListener("pointerdown", forget);
      track.removeEventListener("wheel", forget);
      track.removeEventListener("keydown", forget);
    };
  }, [cards, keys]);

  // With many plans the pill row scrolls too: keep the current pill in it.
  useEffect(() => {
    const row = pillsRef.current;
    const pill = row?.querySelectorAll(".plan-deck__pill")[active];
    if (!row || !pill || row.scrollWidth <= row.clientWidth) return;
    const delta = scrollDelta({ card: pill.getBoundingClientRect(), track: row.getBoundingClientRect() });
    if (Math.abs(delta) >= 1) row.scrollBy({ left: delta, behavior: prefersReducedMotion() ? "instant" : "smooth" });
  }, [active]);

  const go = (index) => {
    preferred.current = index;
    setActive(index);
    scrollToCard(trackRef.current, cards()[index]);
  };

  return (
    <div className={deckClasses(count, bleed)} style={deckStyle(count)}>
      {count > 1 && (
        <div ref={pillsRef} className="plan-deck__pills">
          <div role="group" aria-label={t("pricing.plansNav")} className="plan-deck__pill-row">
            {plans.map((plan, index) => (
              <button
                key={plan.key}
                type="button"
                aria-current={index === active ? "true" : undefined}
                aria-controls={`plan-card-${plan.key}`}
                onClick={() => go(index)}
                className="plan-deck__pill"
              >
                {plan.name}
              </button>
            ))}
          </div>
        </div>
      )}
      <div ref={trackRef} className="plan-deck__track" role="region" aria-label={t("pricing.plansTrack")}>
        {plans.map((plan, index) => (
          <ClassicPlanCard
            key={plan.key}
            id={`plan-card-${plan.key}`}
            index={index}
            plan={plan}
            chars={chars}
            compact={compact}
            raised={raised && plan.highlighted}
            onSwitchCycle={onSwitchCycle}
          />
        ))}
      </div>
    </div>
  );
}

// The same frame with placeholder cards: the skeleton reserves the shape
// of the final deck at every width (no layout shift when plans arrive).
export function PlanDeckSkeleton({ count = 3, bleed = true, compact = false }) {
  return (
    <div className={deckClasses(count, bleed)} style={deckStyle(count)} aria-hidden="true">
      {count > 1 && (
        <div className="plan-deck__pills">
          <div className="plan-deck__pill-row">
            {Array.from({ length: count }, (_, i) => <span key={i} className="plan-deck__pill plan-deck__pill--skeleton" />)}
          </div>
        </div>
      )}
      <div className="plan-deck__track">
        {Array.from({ length: count }, (_, i) => (
          <div key={i} className={`plan-card plan-card--skeleton ${compact ? "plan-card--skeleton-compact" : ""} animate-pulse rounded-card border border-line bg-paper`} />
        ))}
      </div>
    </div>
  );
}
