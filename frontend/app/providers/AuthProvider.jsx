"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { setLocalIdentity } from "@/lib/localIdentity";
import { registerServiceWorker } from "@/lib/registerServiceWorker";
import {
  clearSessionCache,
  isConnectivityFailure,
  readSessionCache,
  writeSessionCache,
} from "@/lib/sessionCache";

import { COMPANY_ACCESS_EVENT, auth, prefs, rbac } from "@/lib/api";
import { clearPendingLogout, flushPendingLogout, markPendingLogout, pendingLogout } from "@/lib/pendingLogout";
import { useI18n } from "./I18nProvider";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [access, setAccess] = useState({});
  const [loading, setLoading] = useState(true);
  // True while the identity on screen came from the local cache because the
  // server could not be reached; the shell shows this state to the user.
  const [offlineSession, setOfflineSession] = useState(false);
  const { hydrateFromServer } = useI18n();

  const signedOut = useCallback(() => {
    clearSessionCache();
    setLocalIdentity(null);
    setUser(null);
    setAccess({});
    setOfflineSession(false);
  }, []);

  const loadSession = useCallback(async () => {
    // A sign-out taken while offline goes to the server before anything
    // else; until it has, this device is signed out — the old cookies must
    // not bring the last cashier's session back.
    if (pendingLogout()) {
      await flushPendingLogout(auth.logout);
      signedOut();
      setLoading(false);
      return null;
    }
    try {
      const [meRes, accessRes] = await Promise.all([auth.me(), rbac.access()]);
      setLocalIdentity(meRes.data);
      setUser(meRes.data);
      setAccess(accessRes.data || {});
      setOfflineSession(false);
      writeSessionCache(meRes.data, accessRes.data);
      // Locale/theme are client-owned (I18nProvider); a fresh session hydrates
      // them from the server only if the user hasn't chosen locally yet.
      try {
        const prefRes = await prefs.get();
        hydrateFromServer(prefRes.data);
      } catch {
        /* no stored prefs / not critical */
      }
      return meRes.data;
    } catch (error) {
      // Only a definite "you are not signed in" (401/403) ends the session.
      // A network drop or a 5xx keeps the last known identity so the app —
      // and the offline queue — stay usable until the server is back.
      const cached = isConnectivityFailure(error) ? readSessionCache() : null;
      if (cached) {
        setLocalIdentity(cached.me);
        setUser(cached.me);
        setAccess(cached.access);
        setOfflineSession(true);
        return cached.me;
      }
      signedOut();
      return null;
    } finally {
      setLoading(false);
    }
  }, [hydrateFromServer, signedOut]);

  useEffect(() => {
    registerServiceWorker();
    loadSession();
  }, [loadSession]);

  // The connection is back: send a sign-out still waiting for it.
  useEffect(() => {
    const onOnline = () => { if (pendingLogout()) flushPendingLogout(auth.logout); };
    window.addEventListener("online", onOnline);
    return () => window.removeEventListener("online", onOnline);
  }, []);

  // A request refused because the platform suspended the company: re-read
  // the identity (it carries company_access) so the shell can react. At
  // most once a minute — every screen's calls fail alike at that moment.
  useEffect(() => {
    let last = 0;
    const onAccess = () => {
      const now = Date.now();
      if (now - last < 60000) return;
      last = now;
      loadSession();
    };
    window.addEventListener(COMPANY_ACCESS_EVENT, onAccess);
    return () => window.removeEventListener(COMPANY_ACCESS_EVENT, onAccess);
  }, [loadSession]);

  const login = useCallback(
    async (email, password) => {
      // The previous session's sign-out goes first: sent after this login it
      // would end the NEW session instead (the cookies are shared). If it
      // still cannot be sent, the login cannot reach the server either.
      if (!(await flushPendingLogout(auth.logout))) clearPendingLogout();
      await auth.login(email, password);
      setLoading(true);
      await loadSession();
    },
    [loadSession]
  );

  // The screen is cleared at once, whatever the network does: a cashier who
  // pressed "Sign out" must never be left signed in on a shared device. The
  // server call ends the session for real (blacklists the refresh token,
  // clears the cookies); when the server cannot be reached the sign-out is
  // kept as pending and sent the moment it answers again.
  const logout = useCallback(async () => {
    markPendingLogout(user?.id ?? null);
    signedOut();
    await flushPendingLogout(auth.logout);
  }, [user?.id, signedOut]);

  const canRead = useCallback(
    (module) => !module || (access[module] && access[module] !== "none"),
    [access]
  );

  const canWrite = useCallback((module) => access[module] === "write", [access]);
  const can = useCallback(
    (capability) => Boolean(user?.capabilities?.[capability]),
    [user]
  );

  const value = {
    user,
    access,
    loading,
    offlineSession,
    login,
    logout,
    canRead,
    canWrite,
    can,
    // Re-reads identity and permissions without a page reload — used after a
    // change that reshapes the app itself, such as picking a business type.
    refresh: loadSession,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
