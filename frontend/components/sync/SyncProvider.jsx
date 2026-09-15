"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import api, { sync } from "@/lib/api";
import { queue, storageHeadroom } from "@/lib/syncQueue";
import { identityScope } from "@/lib/localIdentity";
import { offlineStore, pullCatalogue, requestPersistentStorage } from "@/lib/offlineStore";
import { isStoragePersisted } from "@/lib/installPrompt";
import { useAuth } from "../../app/providers/AuthProvider";

const SyncContext = createContext(null);
export function useSync() {
  const context = useContext(SyncContext);
  if (!context) throw new Error("SyncProvider is required.");
  return context;
}
// For components that may render outside the sync tree (the platform
// console has no offline queue): null instead of a throw.
export function useOptionalSync() {
  return useContext(SyncContext);
}

// navigator.onLine only says whether there is a network interface; a router
// with no upstream (the common failure in the target market) reports "online"
// forever. A real reachability probe against the API decides instead.
const PROBE_INTERVAL_MS = 20000;
const PROBE_TIMEOUT_MS = 3000;
const PULL_INTERVAL_MS = 5 * 60 * 1000;

async function probeServer() {
  try {
    const base = api.defaults.baseURL || "";
    const response = await fetch(`${base}/health/`, {
      method: "GET",
      cache: "no-store",
      credentials: "omit",
      signal: AbortSignal.timeout(PROBE_TIMEOUT_MS),
    });
    return response.ok;
  } catch {
    return false;
  }
}

export function SyncProvider({ children }) {
  const { user } = useAuth();
  const scope = identityScope(user);
  const [online, setOnline] = useState(true);
  const [operations, setOperations] = useState([]);
  const [flushing, setFlushing] = useState(false);
  const [error, setError] = useState("");
  const [legacy, setLegacy] = useState(false);
  const [lastPulledAt, setLastPulledAt] = useState(null);
  const [lastSyncedAt, setLastSyncedAt] = useState(null);
  // Whether the browser has promised not to evict this origin's storage.
  // null until asked; false is the normal answer for an uninstalled tab.
  const [persisted, setPersisted] = useState(null);
  const [storageLow, setStorageLow] = useState(false);
  // client_uuid → {id} for offline sales the server has confirmed, kept in
  // state so the receipt screen can read it synchronously.
  const [receipts, setReceipts] = useState({});
  const onlineRef = useRef(true);
  const busy = useRef(false);
  const pulling = useRef(false);
  const retryAt = useRef(0);
  const failures = useRef(0);

  const refresh = useCallback(async () => {
    try {
      setOperations(scope ? await queue.list(scope) : []);
      setLegacy(queue.hasLegacy());
      const headroom = await storageHeadroom();
      setStorageLow(Boolean(headroom?.low));
    } catch { setError("storage"); }
  }, [scope]);

  const setReachable = useCallback((value) => {
    onlineRef.current = value;
    setOnline(value);
  }, []);

  const flush = useCallback(async (manual = true) => {
    if (!scope || busy.current || !onlineRef.current) return;
    if (!manual && Date.now() < retryAt.current) return;
    busy.current = true;
    setFlushing(true);
    const run = async () => {
      let ops;
      try {
        ops = (await queue.list(scope)).filter((op) => manual || !op.error).slice(0, 100);
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
          await queue.acknowledge(ops, res.data.results, scope);
          const confirmed = {};
          for (const op of ops) {
            const receipt = await queue.confirmation(op.client_uuid, scope);
            if (receipt) confirmed[op.client_uuid] = receipt;
          }
          setReceipts((prev) => ({ ...prev, ...confirmed }));
          setError("");
          failures.current = 0;
          retryAt.current = 0;
          setLastSyncedAt(new Date());
        } catch { setError("storage"); retryAt.current = Date.now() + 60000; }
      } catch (err) {
        if (!err?.response) setReachable(false);
        const status = err?.response?.status;
        // 401/403 after a long outage: the refresh cookie (7 days) expired or
        // the account lost the module. The queue is intact and scoped to this
        // user; what it needs is a fresh sign-in, not another retry.
        setError(status === 409 ? "identity" : status === 401 || status === 403 ? "auth" : "network");
        failures.current += 1;
        retryAt.current = Date.now() + Math.min(300000, 15000 * 2 ** failures.current);
      }
    };
    try {
      if (navigator.locks) await navigator.locks.request(`erp-sync:${scope}`, run);
      else await run();
    } finally { busy.current = false; setFlushing(false); refresh(); }
  }, [scope, user?.company, user?.id, user?.branch, refresh, setReachable]);

  // Mirror the catalogue/customers/suppliers/recent invoices locally so the
  // till keeps working when the server is unreachable. Delta-based via the
  // server's cursor, so after the first full pull each run is small.
  const pull = useCallback(async () => {
    if (!scope || pulling.current || !onlineRef.current) return;
    pulling.current = true;
    try {
      await pullCatalogue(sync, scope);
      const stamp = await offlineStore.getMeta("pulled_at", scope);
      setLastPulledAt(stamp ? new Date(stamp) : new Date());
    } catch (err) {
      if (!err?.response) setReachable(false);
    } finally { pulling.current = false; }
  }, [scope, setReachable]);

  // Ask for durable storage now and again after an install, when the
  // browser is far more likely to say yes; surface the answer so the sync
  // drawer can tell the cashier whether queued sales are actually safe.
  useEffect(() => {
    let active = true;
    const ask = async () => {
      await requestPersistentStorage();
      const granted = await isStoragePersisted();
      if (active) setPersisted(granted);
    };
    ask();
    window.addEventListener("appinstalled", ask);
    return () => { active = false; window.removeEventListener("appinstalled", ask); };
  }, []);

  useEffect(() => {
    refresh();
    if (scope) {
      offlineStore.getMeta("pulled_at", scope)
        .then((stamp) => stamp && setLastPulledAt(new Date(stamp)))
        .catch(() => {});
    }
    let cancelled = false;
    const check = async () => {
      const reachable = navigator.onLine && (await probeServer());
      if (cancelled) return;
      const wasOffline = !onlineRef.current;
      setReachable(reachable);
      if (reachable && wasOffline) { retryAt.current = 0; flush(false); pull(); }
    };
    const up = () => check();
    const down = () => setReachable(false);
    window.addEventListener("online", up);
    window.addEventListener("offline", down);
    window.addEventListener("storage", refresh);
    check().then(() => { flush(false); pull(); });
    const probeTimer = setInterval(check, PROBE_INTERVAL_MS);
    const flushTimer = setInterval(() => flush(false), 15000);
    const pullTimer = setInterval(pull, PULL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(probeTimer);
      clearInterval(flushTimer);
      clearInterval(pullTimer);
      window.removeEventListener("online", up);
      window.removeEventListener("offline", down);
      window.removeEventListener("storage", refresh);
    };
  }, [flush, pull, refresh, scope, setReachable]);

  // Resolves only once the operation is durable; rejects otherwise, and the
  // caller keeps the sale on screen.
  const enqueue = useCallback(async (type, payload) => {
    try { const op = await queue.enqueue(type, payload, scope); refresh(); return op; }
    catch (err) { setError("storage"); throw err; }
  }, [scope, refresh]);

  // A receipt for a sale queued before this page loaded (e.g. the till was
  // rebooted between the sale and the upload) is looked up on demand.
  const lookupReceipt = useCallback(async (id) => {
    const receipt = await queue.confirmation(id, scope);
    if (receipt) setReceipts((prev) => (prev[id] ? prev : { ...prev, [id]: receipt }));
    return receipt;
  }, [scope]);

  return <SyncContext.Provider value={{ online, pending: operations.length, operations,
    flushing, error, legacy, enqueue, flush, refresh, pull, lastPulledAt, lastSyncedAt, persisted,
    storageLow, confirmation: (id) => receipts[id] || null, lookupReceipt }}>{children}</SyncContext.Provider>;
}
