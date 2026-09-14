"use client";

// Attention badges: counts of things that appeared since the user last opened
// a part of the app. The server owns the numbers (core/attention.py); this
// provider fetches them on sign-in, when the tab comes back to the front, on
// a timer, and whenever a screen says it changed something (`refresh`).
// Marking a key seen clears it optimistically and tells the server; if that
// call fails the number comes back rather than silently staying hidden.

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { usePathname } from "next/navigation";

import { attention as attentionApi } from "@/lib/api";
import { useAuth } from "../../app/providers/AuthProvider";
import { useOptionalSync } from "../sync/SyncProvider";

const POLL_MS = 60 * 1000;
const STORAGE_KEY = "erp.attention.v1";
const EMPTY = { counts: {}, tones: {}, total: 0 };

const AttentionContext = createContext({ ...EMPTY, refresh: () => {}, markSeen: () => {} });

export function useAttention() {
  return useContext(AttentionContext);
}

function readCached(userId) {
  try {
    const parsed = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "null");
    return parsed?.userId === userId ? parsed.payload : null;
  } catch { return null; }
}

function writeCached(userId, payload) {
  try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ userId, payload })); } catch { /* ignore */ }
}

export function AttentionProvider({ children }) {
  const { user } = useAuth();
  const userId = user?.id ?? null;
  const pathname = usePathname();
  const [payload, setPayload] = useState(EMPTY);
  const inflight = useRef(null);
  // Clicking a tab and landing on its page happen within the same second, and
  // the landing triggers a refresh. If that GET raced ahead of the POST that
  // records the visit, the cleared badge would come straight back — so every
  // refresh waits for outstanding "seen" calls first.
  const seenInflight = useRef(Promise.resolve());
  // A GET that was already in flight when the user clicked still carries the
  // old number; its response is discarded and one more fetch follows.
  const version = useRef(0);
  // A finished sync (the queue flushed, or a delta pull) is exactly when new
  // items may have appeared; piggy-back on it instead of a second timer.
  const sync = useOptionalSync();
  const syncStamp = sync ? `${sync.lastSyncedAt || ""}|${sync.lastPulledAt || ""}` : "";

  // Show the last known numbers immediately after a reload or while offline.
  useEffect(() => {
    if (!userId) { setPayload(EMPTY); return; }
    const cached = readCached(userId);
    if (cached) setPayload(cached);
  }, [userId]);

  const refresh = useCallback(() => {
    if (!userId) return Promise.resolve();
    if (inflight.current) return inflight.current;
    const started = version.current;
    inflight.current = seenInflight.current
      .then(() => attentionApi.get())
      .then((response) => {
        if (started !== version.current) return;
        const next = {
          counts: response.data?.counts || {},
          tones: response.data?.tones || {},
          total: Number(response.data?.total) || 0,
        };
        setPayload(next);
        writeCached(userId, next);
      })
      .catch(() => { /* offline or transient: keep what we have */ })
      .finally(() => {
        inflight.current = null;
        if (started !== version.current) refresh();
      });
    return inflight.current;
  }, [userId]);

  useEffect(() => {
    if (!userId || !syncStamp) return;
    refresh();
  }, [syncStamp, userId, refresh]);

  useEffect(() => {
    if (!userId) return undefined;
    refresh();
    const timer = setInterval(refresh, POLL_MS);
    const onVisible = () => { if (document.visibilityState === "visible") refresh(); };
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", refresh);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", refresh);
    };
  }, [userId, refresh]);

  const markSeen = useCallback((key) => {
    if (!key) return;
    let hadCount = false;
    setPayload((current) => {
      if (!current.counts[key]) return current;
      hadCount = true;
      const counts = { ...current.counts };
      delete counts[key];
      const tones = { ...current.tones };
      delete tones[key];
      const next = { counts, tones, total: Object.values(counts).reduce((a, b) => a + b, 0) };
      writeCached(userId, next);
      return next;
    });
    // Always tell the server (it moves the "since" point even when the badge
    // was already zero); on failure re-fetch so a hidden number reappears.
    version.current += 1;
    const call = attentionApi.seen(key).catch(() => { if (hadCount) refresh(); });
    seenInflight.current = seenInflight.current.then(() => call, () => call);
  }, [userId, refresh]);

  const value = useMemo(() => ({ ...payload, refresh, markSeen }), [payload, refresh, markSeen]);

  // The browser tab carries the total, the way mail clients do. Pages set
  // their own titles on navigation, so the prefix is re-applied per route.
  useEffect(() => {
    if (typeof document === "undefined") return;
    const apply = () => {
      const base = document.title.replace(/^\(\d+\+?\)\s*/, "");
      const wanted = payload.total > 0 ? `(${payload.total > 99 ? "99+" : payload.total}) ${base}` : base;
      if (document.title !== wanted) document.title = wanted;
    };
    apply();
    const timer = setTimeout(apply, 300);
    try {
      if (payload.total > 0 && navigator.setAppBadge) navigator.setAppBadge(payload.total);
      else if (navigator.clearAppBadge) navigator.clearAppBadge();
    } catch { /* unsupported */ }
    return () => clearTimeout(timer);
  }, [payload.total, pathname]);

  return <AttentionContext.Provider value={value}>{children}</AttentionContext.Provider>;
}
