"use client";

import { useEffect, useRef } from "react";

import { DURATION, EASE_CSS } from "./motion";
import { useReducedMotionSafe } from "./useReducedMotionSafe";

// A quick fade-in (150 ms) of a tab's content when the tab changes. Returns
// a ref for the element that holds the content.
//
// Fade IN only, on the element already on screen: nothing is remounted,
// nothing waits for the old tab to fade out, and the new content takes
// clicks and keys from its first frame — the fade never delays work.
// Skipped on first paint, under reduced motion, and when `disabled` (the
// till: nothing moves on the path between a scan and the next).
export function useTabFade(value, { disabled = false } = {}) {
  const ref = useRef(null);
  const previous = useRef(value);
  const reduced = useReducedMotionSafe();
  useEffect(() => {
    if (previous.current === value) return;
    previous.current = value;
    const el = ref.current;
    if (!el || disabled || reduced || typeof el.animate !== "function") return;
    el.animate([{ opacity: 0.35 }, { opacity: 1 }], {
      duration: DURATION.fast * 1000,
      easing: EASE_CSS,
    });
  }, [value, disabled, reduced]);
  return ref;
}
