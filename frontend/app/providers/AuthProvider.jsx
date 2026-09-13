"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { setLocalIdentity } from "@/lib/localIdentity";

import { auth, prefs, rbac } from "@/lib/api";
import { useI18n } from "./I18nProvider";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [access, setAccess] = useState({});
  const [loading, setLoading] = useState(true);
  const { hydrateFromServer } = useI18n();

  const loadSession = useCallback(async () => {
    try {
      const [meRes, accessRes] = await Promise.all([auth.me(), rbac.access()]);
      setLocalIdentity(meRes.data);
      setUser(meRes.data);
      setAccess(accessRes.data || {});
      // Locale/theme are client-owned (I18nProvider); a fresh session hydrates
      // them from the server only if the user hasn't chosen locally yet.
      try {
        const prefRes = await prefs.get();
        hydrateFromServer(prefRes.data);
      } catch {
        /* no stored prefs / not critical */
      }
      return meRes.data;
    } catch {
      setLocalIdentity(null);
      setUser(null);
      setAccess({});
      return null;
    } finally {
      setLoading(false);
    }
  }, [hydrateFromServer]);

  useEffect(() => {
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
      setLocalIdentity(null);
      setUser(null);
      setAccess({});
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
