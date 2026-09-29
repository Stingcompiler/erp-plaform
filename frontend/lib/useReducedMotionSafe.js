"use client";

import { useSyncExternalStore } from "react";

// Whether the person asked the system for less motion
// (`prefers-reduced-motion: reduce`), kept current if they change it while
// the app is open.
//
// "Safe": on the server and during hydration there is no media query to
// ask, and the answer is TRUE — no motion — until the browser says
// otherwise. An animation that starts on mount therefore never plays its
// first frames for someone who asked for none. framer-motion's own
// useReducedMotion answers null there, which reads as "animate".

const QUERY = "(prefers-reduced-motion: reduce)";

function subscribe(onChange) {
  if (typeof window === "undefined" || !window.matchMedia) return () => {};
  const list = window.matchMedia(QUERY);
  list.addEventListener?.("change", onChange);
  return () => list.removeEventListener?.("change", onChange);
}

export function prefersReducedMotion() {
  if (typeof window === "undefined" || !window.matchMedia) return true;
  return window.matchMedia(QUERY).matches;
}

// Printing (or a print preview) is the end state too: a figure caught
// mid-count must not go on paper.
export function isPrinting() {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia("print").matches;
}

const serverSnapshot = () => true;

export function useReducedMotionSafe() {
  return useSyncExternalStore(subscribe, prefersReducedMotion, serverSnapshot);
}
