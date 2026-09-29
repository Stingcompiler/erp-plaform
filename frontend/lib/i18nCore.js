// The language plumbing every page needs, with no strings in it: which
// languages exist, their direction, and how a key is looked up in a catalog.
// The catalogs are separate modules so a page loads only its own:
//
//   lib/i18n.js       the whole app (every namespace), for the workspace,
//                     sign-in and the other app routes;
//   lib/publicI18n.js the public marketing pages only (landing, pricing,
//                     product, register, track, content pages).
//
// A route group's layout hands its catalog to <I18nCatalog> (app/providers/
// I18nProvider.jsx); useI18n().t reads from the nearest one.

export const LANGUAGES = [
  { code: "en", label: "English", native: "English", dir: "ltr" },
  { code: "ar", label: "Arabic", native: "العربية", dir: "rtl" },
];

export const DEFAULT_LANGUAGE = "ar";
export const FALLBACK_LANGUAGE = "en";

export function dirFor(lang) {
  const entry = LANGUAGES.find((l) => l.code === lang);
  return entry ? entry.dir : "rtl";
}

function lookup(obj, path) {
  return path.split(".").reduce((acc, part) => (acc == null ? acc : acc[part]), obj);
}

// `key` in `catalog` ({ en, ar }) for `lang`, falling back to English, then
// to the key itself — so a missing translation is visible, never a crash.
// {name} placeholders are filled from `vars`.
export function translateFrom(catalog, lang, key, vars) {
  let value = catalog ? lookup(catalog[lang], key) : undefined;
  if (value == null && catalog) value = lookup(catalog[FALLBACK_LANGUAGE], key);
  if (value == null) return key;
  if (vars) {
    return value.replace(/\{(\w+)\}/g, (m, name) =>
      name in vars ? String(vars[name]) : m
    );
  }
  return value;
}
