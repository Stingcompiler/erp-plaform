"use client";

import { useEffect, useLayoutEffect, useRef } from "react";

import { EASE_CSS, ROUTE_ENTER, routeEnterApplies, routeEnterKeyframes } from "./motion";
import { isPrinting, prefersReducedMotion } from "./useReducedMotionSafe";

const useIsoLayoutEffect = typeof window === "undefined" ? useEffect : useLayoutEffect;

// The workspace content's entrance when the route changes: a 180 ms fade and
// 6 px rise of the element the returned ref is on (the shell's <main>).
//
// It starts in a layout effect, before the new page's first paint, so the
// page is never seen at rest and then jumping. It is a Web Animation with no
// fill: when it ends (or is cancelled by the next navigation) the element
// has no transform or opacity of its own left. Nothing is remounted and
// focus is untouched. Skipped on first paint, onto the till (/sales), under
// reduced motion and while printing (lib/motion.js routeEnterApplies).
export function useRouteEnter(pathname) {
  const ref = useRef(null);
  const previous = useRef(pathname);
  useIsoLayoutEffect(() => {
    const from = previous.current;
    previous.current = pathname;
    const el = ref.current;
    if (!el || !routeEnterApplies(from, pathname)) return undefined;
    if (prefersReducedMotion() || isPrinting() || typeof el.animate !== "function") return undefined;
    const animation = el.animate(routeEnterKeyframes(), {
      duration: ROUTE_ENTER.duration,
      easing: EASE_CSS,
    });
    return () => animation.cancel();
  }, [pathname]);
  return ref;
}
