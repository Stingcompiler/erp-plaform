"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { sync } from "@/lib/api";
import { queue } from "@/lib/syncQueue";

const SyncContext = createContext(null);

const NOOP = {
  online: true,
  pending: 0,
  flushing: false,
  enqueue: () => {},
  flush: async () => {},
  refresh: () => {},
};

export function useSync() {
  return useContext(SyncContext) || NOOP;
}

function uuid() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  return "xxxxxxxxxxxx".replace(/x/g, () => ((Math.random() * 16) | 0).toString(16));
}

export function SyncProvider({ children }) {
  const [online, setOnline] = useState(true);
  const [pending, setPending] = useState(0);
  const [flushing, setFlushing] = useState(false);

  const refresh = useCallback(() => setPending(queue.count()), []);

  useEffect(() => {
    refresh();
    setOnline(typeof navigator === "undefined" ? true : navigator.onLine);
    const up = () => setOnline(true);
    const down = () => setOnline(false);
    window.addEventListener("online", up);
    window.addEventListener("offline", down);
    return () => {
      window.removeEventListener("online", up);
      window.removeEventListener("offline", down);
    };
  }, [refresh]);

  const flush = useCallback(async () => {
    const ops = queue.list();
    if (ops.length === 0 || flushing) return;
    setFlushing(true);
    try {
      const res = await sync.push({
        batch_uuid: uuid(),
        device_id: "web",
        operations: ops.map((o) => ({
          op_type: o.op_type,
          client_uuid: o.client_uuid,
          payload: o.payload,
        })),
      });
      // On a successful push (applied, duplicate, or replay) the batch is
      // durably recorded server-side, so clear what we sent.
      if (res?.status === 200 || res?.status === 201) {
        queue.removeByUuids(ops.map((o) => o.client_uuid));
      }
    } catch {
      /* still offline or server error — keep the queue for the next attempt */
    } finally {
      refresh();
      setFlushing(false);
    }
  }, [flushing, refresh]);

  // Auto-drain whenever we come (back) online and there's a backlog.
  useEffect(() => {
    if (online && pending > 0) flush();
  }, [online, pending, flush]);

  const enqueue = useCallback(
    (opType, payload) => {
      queue.enqueue(opType, payload);
      refresh();
    },
    [refresh]
  );

  const value = { online, pending, flushing, enqueue, flush, refresh };
  return <SyncContext.Provider value={value}>{children}</SyncContext.Provider>;
}
