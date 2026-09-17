"use client";

import { useCallback } from "react";

import { useSync } from "@/components/sync/SyncProvider";
import { useAttention } from "@/components/attention/AttentionProvider";

// One path for every branch-level write (PROJECT_RULES Rule #2): try the
// live endpoint when the server is reachable, otherwise — or when the request
// dies on the wire — queue the same payload for /api/sync/push/, which
// applies it through the same serializer. `payload.client_uuid` is the
// idempotency key, so the caller must mint it once per user action and reuse
// it across retries; the queue keeps the first body it saw for that key.
//
// Resolves to { queued: false, data } after a live write, or
// { queued: true, op } after queueing. A server-side rejection (4xx) is
// thrown untouched so the form can show the validation message.
export function useOfflineMutation() {
  const { online, enqueue } = useSync();
  const { refresh } = useAttention();
  return useCallback(
    async (opType, request, payload) => {
      if (!payload?.client_uuid) throw new Error(`${opType}: payload needs a client_uuid`);
      // `enqueue` resolves only once IndexedDB has COMMITTED the row. It is
      // awaited here on purpose: returning the pending promise made callers
      // report "saved for upload" before the write was durable, and a failed
      // write became an unhandled rejection — the receipt or return silently
      // disappeared.
      if (!online) return { queued: true, op: await enqueue(opType, payload) };
      try {
        const response = await request(payload);
        refresh();
        return { queued: false, data: response.data };
      } catch (error) {
        if (error?.code === "ERR_NETWORK" || !error?.response) {
          return { queued: true, op: await enqueue(opType, payload) };
        }
        throw error;
      }
    },
    [online, enqueue, refresh],
  );
}
