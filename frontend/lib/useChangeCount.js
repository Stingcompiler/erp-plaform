"use client";

import { useState } from "react";

import { countChange } from "./motion";

// How many times `value` has changed since it was first known. A caller keys
// a highlight on it (<span key={n} className={n ? "change-flash" : ""}>) so
// the highlight plays once per change and never on first load. Derived while
// rendering, so the highlight is in the same frame as the new value.
export function useChangeCount(value) {
  const [state, setState] = useState({ value, count: 0 });
  if (!Object.is(state.value, value)) {
    const next = countChange(state, value);
    setState(next);
    return next.count;
  }
  return state.count;
}
