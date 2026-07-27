"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { DEFAULT_LANGUAGE, LANGUAGES, dirFor, translate } from "@/lib/i18n";
import { prefs } from "@/lib/api";

// Locale + theme live here (not in AuthProvider) so public pages — the landing
// page and login — are fully bilingual and themed without a session. The client
// is the source of truth, persisted in localStorage + a cookie; for logged-in
// users, changes are also pushed to the server (best-effort) for cross-device
// continuity, and a fresh session can hydrate these once from the server.

const I18nContext = createContext(null);

const LANG_KEY = "erp.language";
const THEME_KEY = "erp.theme";
const THEMES = ["light", "dark", "system"];

function readStored(key, valid, fallback) {
  if (typeof window === "undefined") return fallback;
  try {
    const v = window.localStorage.getItem(key);
    return v && valid.includes(v) ? v : fallback;
  } catch {
    return fallback;
  }
}

function writeCookie(name, value) {
  try {
    document.cookie = `${name}=${value};path=/;max-age=31536000;samesite=lax`;
  } catch {
    /* ignore */
  }
}

function systemPrefersDark() {
  return (
    typeof window !== "undefined" &&
    window.matchMedia &&
    window.matchMedia("(prefers-color-scheme: dark)").matches
  );
}

export function I18nProvider({ children }) {
  const langCodes = LANGUAGES.map((l) => l.code);
  const [language, setLanguageState] = useState(DEFAULT_LANGUAGE);
  const [theme, setThemeState] = useState("system");
  // Tracks whether the user has made an explicit choice this session, so a
  // late-arriving server hydrate doesn't clobber a deliberate toggle.
  const userTouched = useRef(false);

  // Hydrate from localStorage on mount (client only).
  useEffect(() => {
    setLanguageState(readStored(LANG_KEY, langCodes, DEFAULT_LANGUAGE));
    setThemeState(readStored(THEME_KEY, THEMES, "system"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Reflect language + direction on <html> whenever language changes.
  useEffect(() => {
    const dir = dirFor(language);
    const root = document.documentElement;
    root.setAttribute("lang", language);
    root.setAttribute("dir", dir);
  }, [language]);

  // Reflect theme on <html> (.dark class), reacting to system changes too.
  useEffect(() => {
    const apply = () => {
      const dark = theme === "dark" || (theme === "system" && systemPrefersDark());
      document.documentElement.classList.toggle("dark", dark);
    };
    apply();
    if (theme === "system" && window.matchMedia) {
      const mq = window.matchMedia("(prefers-color-scheme: dark)");
      mq.addEventListener("change", apply);
      return () => mq.removeEventListener("change", apply);
    }
  }, [theme]);

  const syncServer = useCallback((body) => {
    // Best-effort: silently ignored when logged out (401) or offline.
    prefs.update(body).catch(() => {});
  }, []);

  const setLanguage = useCallback(
    (lang, { sync = true } = {}) => {
      if (!langCodes.includes(lang)) return;
      userTouched.current = true;
      setLanguageState(lang);
      try {
        window.localStorage.setItem(LANG_KEY, lang);
      } catch {
        /* ignore */
      }
      writeCookie("erp_language", lang);
      if (sync) syncServer({ language: lang });
    },
    [langCodes, syncServer]
  );

  const toggleLanguage = useCallback(() => {
    setLanguage(language === "ar" ? "en" : "ar");
  }, [language, setLanguage]);

  const setTheme = useCallback(
    (next, { sync = true } = {}) => {
      if (!THEMES.includes(next)) return;
      userTouched.current = true;
      setThemeState(next);
      try {
        window.localStorage.setItem(THEME_KEY, next);
      } catch {
        /* ignore */
      }
      if (sync) syncServer({ theme: next });
    },
    [syncServer]
  );

  const cycleTheme = useCallback(() => {
    const idx = THEMES.indexOf(theme);
    setTheme(THEMES[(idx + 1) % THEMES.length]);
  }, [theme, setTheme]);

  // Called once by AuthProvider after a session loads. Only applies the
  // server's stored prefs if the user hasn't already chosen locally.
  const hydrateFromServer = useCallback((serverPrefs) => {
    if (userTouched.current || !serverPrefs) return;
    if (serverPrefs.language && !readStored(LANG_KEY, ["en", "ar"], null)) {
      setLanguageState(serverPrefs.language);
    }
    if (serverPrefs.theme && !readStored(THEME_KEY, THEMES, null)) {
      setThemeState(serverPrefs.theme);
    }
  }, []);

  const t = useCallback(
    (key, vars) => translate(language, key, vars),
    [language]
  );

  const value = useMemo(
    () => ({
      language,
      dir: dirFor(language),
      theme,
      t,
      setLanguage,
      toggleLanguage,
      setTheme,
      cycleTheme,
      hydrateFromServer,
    }),
    [language, theme, t, setLanguage, toggleLanguage, setTheme, cycleTheme, hydrateFromServer]
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used within I18nProvider");
  return ctx;
}
