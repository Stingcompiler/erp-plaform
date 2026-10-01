"use client";

import { useEffect, useState } from "react";

import { exitDuration } from "./navMotion";
import { prefersReducedMotion } from "./useReducedMotionSafe";

// Keeps something that is closing on screen for `exitMs` so it can animate
// out (the phone drawer, the marketing menu). `state` is "open" or
// "closed"; while closing the caller renders it inert, so it takes no
// clicks or focus — nothing waits for the animation. Opening is immediate.
// Under reduced motion it unmounts at once.
export function usePresence(open, exitMs) {
  const [mounted, setMounted] = useState(open);
  if (open && !mounted) setMounted(true);
  useEffect(() => {
    if (open || !mounted) return undefined;
    const ms = exitDuration(exitMs, prefersReducedMotion());
    if (!ms) {
      setMounted(false);
      return undefined;
    }
    const timer = window.setTimeout(() => setMounted(false), ms);
    return () => window.clearTimeout(timer);
  }, [open, mounted, exitMs]);
  return { mounted: open || mounted, state: open ? "open" : "closed" };
}
