"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { sync } from "@/lib/api";
import { queue } from "@/lib/syncQueue";
import { identityScope } from "@/lib/localIdentity";
import { useAuth } from "../../app/providers/AuthProvider";

const SyncContext = createContext(null);
export function useSync() {
  const context = useContext(SyncContext);
  if (!context) throw new Error("SyncProvider is required.");
  return context;
}

export function SyncProvider({ children }) {
  const { user } = useAuth();
  const scope = identityScope(user);
  const [online, setOnline] = useState(true);
  const [operations, setOperations] = useState([]);
  const [flushing, setFlushing] = useState(false);
  const [error, setError] = useState("");
  const [legacy, setLegacy] = useState(false);
  const busy = useRef(false);
  const retryAt = useRef(0);
  const failures = useRef(0);
  const refresh = useCallback(() => {
    try {
      setOperations(scope ? queue.list(scope) : []);
      setLegacy(queue.hasLegacy());
    } catch { setError("storage"); }
  }, [scope]);

  const flush = useCallback(async (manual = true) => {
    if (!scope || busy.current || !navigator.onLine) return;
    if (!manual && Date.now() < retryAt.current) return;
    busy.current = true;
    setFlushing(true);
    const run = async () => {
      let ops;
      try {
        ops = queue.list(scope).filter((op) => manual || !op.error).slice(0, 100);
        if (!ops.length) return;
      } catch { setError("storage"); return; }
      try {
        const res = await sync.push({
          batch_uuid: crypto.randomUUID(), device_id: "web",
          expected_company: user.company, expected_user: user.id,
          expected_branch: user.branch ?? null,
          operations: ops.map(({ op_type, client_uuid, payload }) => ({ op_type, client_uuid, payload })),
        });
        try {
          queue.acknowledge(ops, res.data.results, scope);
          setError("");
          failures.current = 0;
          retryAt.current = 0;
        } catch { setError("storage"); retryAt.current = Date.now() + 60000; }
      } catch (err) {
        setError(err?.response?.status === 409 ? "identity" : "network");
        failures.current += 1;
        retryAt.current = Date.now() + Math.min(300000, 15000 * 2 ** failures.current);
      }
    };
    try {
      if (navigator.locks) await navigator.locks.request(`erp-sync:${scope}`, run);
      else await run();
    } finally { busy.current = false; setFlushing(false); refresh(); }
  }, [scope, user?.company, user?.id, user?.branch, refresh]);

  useEffect(() => {
    refresh();
    setOnline(navigator.onLine);
    const up = () => { setOnline(true); retryAt.current = 0; flush(false); };
    const down = () => setOnline(false);
    window.addEventListener("online", up);
    window.addEventListener("offline", down);
    window.addEventListener("storage", refresh);
    const timer = setInterval(() => flush(false), 15000);
    flush(false);
    return () => {
      clearInterval(timer);
      window.removeEventListener("online", up);
      window.removeEventListener("offline", down);
      window.removeEventListener("storage", refresh);
    };
  }, [flush, refresh]);

  const enqueue = useCallback((type, payload) => {
    try { const op = queue.enqueue(type, payload, scope); refresh(); return op; }
    catch (err) { setError("storage"); throw err; }
  }, [scope, refresh]);

  return <SyncContext.Provider value={{ online, pending: operations.length, operations,
    flushing, error, legacy, enqueue, flush, refresh, confirmation: (id) => queue.confirmation(id, scope) }}>{children}</SyncContext.Provider>;
}
