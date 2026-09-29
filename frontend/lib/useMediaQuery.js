"use client";

import { useCallback, useSyncExternalStore } from "react";

// Whether a media query matches, kept current. `serverValue` is the answer
// on the server and during hydration (there is no window to ask).
export function useMediaQuery(query, serverValue = false) {
  const subscribe = useCallback((onChange) => {
    if (typeof window === "undefined" || !window.matchMedia) return () => {};
    const list = window.matchMedia(query);
    list.addEventListener?.("change", onChange);
    return () => list.removeEventListener?.("change", onChange);
  }, [query]);
  const snapshot = () => (typeof window !== "undefined" && window.matchMedia ? window.matchMedia(query).matches : serverValue);
  return useSyncExternalStore(subscribe, snapshot, () => serverValue);
}
