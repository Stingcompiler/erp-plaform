"use client";

import { useCallback, useRef } from "react";

// One idempotency key per user action, not per click. A drawer that minted a
// fresh client_uuid on every press turned "the gateway timed out, press Save
// again" into two refunds, two payments or two stock adjustments. Keys live
// until reset(): call it when the drawer opens on a new subject and after a
// confirmed success.
export function useStableIds() {
  const ids = useRef(new Map());
  const idFor = useCallback((slot = "main") => {
    if (!ids.current.has(slot)) ids.current.set(slot, crypto.randomUUID());
    return ids.current.get(slot);
  }, []);
  const reset = useCallback(() => { ids.current.clear(); }, []);
  return { idFor, reset };
}
