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
import { usePathname, useRouter } from "next/navigation";

import { DEFAULT_LANGUAGE, LANGUAGES, dirFor, translate } from "@/lib/i18n";
import { counterpartPath, localizePath, marketingLanguage } from "@/lib/locale";
import { prefs } from "@/lib/api";

// Locale + theme live here (not in AuthProvider) so public pages — the landing
// page and login — are fully bilingual and themed without a session. The client
// is the source of truth, persisted in localStorage + a cookie; for logged-in
// users, changes are also pushed to the server (best-effort) for cross-device
// continuity, and a fresh session can hydrate these once from the server.
//
// On the public marketing pages the language is part of the URL instead
// (lib/locale.js): / is Arabic, /en/ is English, and switching navigates to
// the counterpart page so the address always matches what is on screen and
// each language is indexable on its own. The stored preference still decides
// where a returning visitor lands.

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

// usePathname() has no query string or hash; the counterpart page must keep
// both (/register?plan=3 -> /en/register?plan=3). Client only.
function currentLocation(pathname) {
  return pathname + window.location.search + window.location.hash;
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
  const pathname = usePathname();
  const router = useRouter();
  // "ar" | "en" on a public marketing page, null inside the app.
  const routeLanguage = marketingLanguage(pathname);
  const [language, setLanguageState] = useState(routeLanguage ?? DEFAULT_LANGUAGE);
  const [theme, setThemeState] = useState("system");
  // Tracks whether the user has made an explicit choice this session, so a
  // late-arriving server hydrate doesn't clobber a deliberate toggle.
  const userTouched = useRef(false);

  // Hydrate from localStorage on mount (client only). On a marketing page the
  // URL wins; a stored preference for the other language sends the visitor
  // to the counterpart page instead of re-rendering this one in place.
  useEffect(() => {
    const stored = readStored(LANG_KEY, langCodes, null);
    setThemeState(readStored(THEME_KEY, THEMES, "system"));
    if (routeLanguage) {
      if (stored && stored !== routeLanguage) {
        router.replace(counterpartPath(currentLocation(pathname), stored));
      }
      return;
    }
    setLanguageState(stored ?? DEFAULT_LANGUAGE);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Client-side navigation between / and /en/ (or into the app) re-derives
  // the language from the new URL.
  useEffect(() => {
    if (routeLanguage) setLanguageState(routeLanguage);
  }, [routeLanguage]);

  // Reflect language + direction on <html> whenever language changes, and
  // tell the API too. The cookie used to be written only on a manual toggle,
  // so a user who never switched sent none and LocaleMiddleware fell back to
  // the browser's Accept-Language — an Arabic screen got English refusals.
  useEffect(() => {
    const dir = dirFor(language);
    const root = document.documentElement;
    root.setAttribute("lang", language);
    root.setAttribute("dir", dir);
    writeCookie("erp_language", language);
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
      if (routeLanguage && lang !== routeLanguage) {
        router.push(counterpartPath(currentLocation(pathname), lang));
      }
    },
    [langCodes, syncServer, routeLanguage, pathname, router]
  );

  // A marketing href written for the Arabic root, in the page's language:
  // href("/pricing") is "/en/pricing" on an English page. App routes such as
  // /login are never prefixed; pass them through untouched.
  const href = useCallback(
    (path) => localizePath(path, routeLanguage),
    [routeLanguage]
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
  // server's stored prefs if the user hasn't already chosen locally. On a
  // marketing page the URL already names the language, so a signed-in
  // visitor opening /en/ deliberately is not flipped back to Arabic.
  const hydrateFromServer = useCallback(
    (serverPrefs) => {
      if (userTouched.current || !serverPrefs) return;
      if (serverPrefs.language && !routeLanguage && !readStored(LANG_KEY, ["en", "ar"], null)) {
        setLanguageState(serverPrefs.language);
      }
      if (serverPrefs.theme && !readStored(THEME_KEY, THEMES, null)) {
        setThemeState(serverPrefs.theme);
      }
    },
    [routeLanguage]
  );

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
      href,
      setLanguage,
      toggleLanguage,
      setTheme,
      cycleTheme,
      hydrateFromServer,
    }),
    [language, theme, t, href, setLanguage, toggleLanguage, setTheme, cycleTheme, hydrateFromServer]
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used within I18nProvider");
  return ctx;
}
