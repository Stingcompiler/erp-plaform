"use client";

import { useEffect } from "react";

import { isPrinting, prefersReducedMotion } from "@/lib/useReducedMotionSafe";

// Cards on the public pages fade up once as they scroll into view.
//
// Every `.mk-reveal` element under `ref` is in the HTML fully visible; this
// hook, after hydration, arms only the ones still below the fold
// (data-reveal-state="armed": transparent, 12 px low — globals.css) and
// marks each "in" when it first enters the viewport. So nothing on screen
// ever blinks out, a no-JS visitor or a crawler sees every card, and under
// reduced motion (or printing) nothing is armed at all.
export function useRevealOnce(ref) {
  useEffect(() => {
    const root = ref.current;
    if (!root || typeof IntersectionObserver === "undefined") return undefined;
    if (prefersReducedMotion() || isPrinting()) return undefined;
    const fold = window.innerHeight;
    const items = Array.from(root.querySelectorAll(".mk-reveal")).filter(
      (el) => !el.dataset.revealState && el.getBoundingClientRect().top > fold,
    );
    if (!items.length) return undefined;
    for (const el of items) el.dataset.revealState = "armed";
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          entry.target.dataset.revealState = "in";
          observer.unobserve(entry.target);
        }
      },
      { rootMargin: "0px 0px -8% 0px" },
    );
    for (const el of items) observer.observe(el);
    return () => {
      observer.disconnect();
      // Never leave a card armed (invisible) behind an observer that is gone.
      for (const el of items) {
        if (el.dataset.revealState === "armed") delete el.dataset.revealState;
      }
    };
  }, [ref]);
}
