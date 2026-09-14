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

import { auth, prefs, rbac } from "@/lib/api";
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

  const loadSession = useCallback(async () => {
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
      clearSessionCache();
      setLocalIdentity(null);
      setUser(null);
      setAccess({});
      setOfflineSession(false);
      return null;
    } finally {
      setLoading(false);
    }
  }, [hydrateFromServer]);

  useEffect(() => {
    registerServiceWorker();
    loadSession();
  }, [loadSession]);

  const login = useCallback(
    async (email, password) => {
      await auth.login(email, password);
      setLoading(true);
      await loadSession();
    },
    [loadSession]
  );

  const logout = useCallback(async () => {
    try {
      await auth.logout();
    } finally {
      clearSessionCache();
      setLocalIdentity(null);
      setUser(null);
      setAccess({});
      setOfflineSession(false);
    }
  }, []);

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
