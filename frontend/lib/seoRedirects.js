// Pure helpers for the «التحويلات» / "Redirects" tab of /platform-seo
// (API /api/platform/seo/redirects/, backend website/redirects.py). They
// mirror the backend's normalisation and its instant rules (protected paths,
// self-redirect, another site) so the form can say what is wrong while the
// team types; chains, loops and duplicates are checked by the server's
// `check` action. No React here, so tests/seoRedirects.test.mjs can run it.

import { PRIVATE_PATH_PREFIXES, SITE_URL } from "./site.js";

export const PUBLIC_HOSTS = ["vezano.app", "www.vezano.app", "pro.vezano.app"];
export const STATUS_CODES = [301, 302];
export const EMPTY_REDIRECT = { source_path: "", target: "", status_code: 301, is_active: true, allow_external: false, note: "" };

// Same lists as backend website/redirects.py PROTECTED_PREFIXES / _EXACT.
const PROTECTED_PREFIXES = [
  "/api", "/admin", "/_next", "/static", "/media", "/icons", "/email", "/platform",
  "/forgot-password", "/reset-password",
  ...PRIVATE_PATH_PREFIXES.map((prefix) => prefix.replace(/\/+$/, "")),
];
const PROTECTED_EXACT = new Set([
  "/", "/en", "/s", "/404", "/sw.js", "/manifest.webmanifest", "/robots.txt", "/sitemap.xml",
  "/sitemap-sites.xml", "/favicon.ico", "/index.txt",
]);
const DASH_PREFIXES = new Set(["/platform"]);
// eslint-disable-next-line no-control-regex
const UNSAFE = /[\s<>"'`\\\u0000-\u001f\u007f]/;

function decode(path) {
  try {
    return decodeURIComponent(path);
  } catch {
    return path;
  }
}

// Leading slash, single slashes, no trailing slash, lowercase.
export function collapsePath(path) {
  const parts = String(path || "").split("/").filter(Boolean);
  return `/${parts.join("/")}`.toLowerCase();
}

function urlOf(text) {
  try {
    return new URL(text.startsWith("//") ? `https:${text}` : text);
  } catch {
    return null;
  }
}

// { path, error } where error is an i18n key under platformSeo.redirects.errors.
export function normalizeSource(value) {
  let raw = String(value ?? "").trim();
  if (!raw) return { path: "", error: "sourceRequired" };
  if (raw.includes("://") || raw.startsWith("//")) {
    const url = urlOf(raw);
    if (!url || !PUBLIC_HOSTS.includes(url.hostname.toLowerCase())) return { path: "", error: "sourceHost" };
    if (url.search || url.hash) return { path: "", error: "sourceQuery" };
    raw = url.pathname || "/";
  }
  if (raw.includes("?") || raw.includes("#")) return { path: "", error: "sourceQuery" };
  raw = decode(raw);
  if (UNSAFE.test(raw)) return { path: "", error: "sourceCharacters" };
  const path = collapsePath(raw);
  if (path.length > 255) return { path: "", error: "sourceLong" };
  return { path, error: null };
}

function covered(key, prefix) {
  if (key === prefix || key.startsWith(`${prefix}/`)) return true;
  return DASH_PREFIXES.has(prefix) && key.startsWith(`${prefix}-`);
}

function withoutLanguage(key) {
  if (key === "/en" || key.startsWith("/en/")) return key.slice(3) || "/";
  return key;
}

export function isProtected(key) {
  return [key, withoutLanguage(key)].some(
    (candidate) => PROTECTED_EXACT.has(candidate) || PROTECTED_PREFIXES.some((prefix) => covered(candidate, prefix)),
  );
}

// { key, external, error }: the page a target lands on (null for another site).
export function targetKey(target, allowExternal = false) {
  const value = String(target ?? "").trim();
  if (!value) return { key: null, external: false, error: "targetRequired" };
  if (value.length > 500) return { key: null, external: false, error: "targetLong" };
  if (UNSAFE.test(value)) return { key: null, external: false, error: "targetCharacters" };
  if (value.startsWith("/")) {
    if (value.startsWith("//")) return { key: null, external: false, error: "targetDoubleSlash" };
    return { key: collapsePath(decode(value.split(/[?#]/)[0])), external: false, error: null };
  }
  const url = urlOf(value);
  if (!url || url.protocol !== "https:" || !url.hostname) return { key: null, external: false, error: "targetScheme" };
  if (url.username || url.password) return { key: null, external: false, error: "targetCredentials" };
  if (PUBLIC_HOSTS.includes(url.hostname.toLowerCase())) {
    return { key: collapsePath(decode(url.pathname)), external: false, error: null };
  }
  if (!allowExternal) return { key: null, external: true, error: "targetExternal" };
  return { key: null, external: true, error: null };
}

// The rules the form can judge on its own: { source_path?, target? } as i18n
// keys (platformSeo.redirects.errors.*), plus the normalised source.
export function localErrors(draft) {
  const errors = {};
  const source = normalizeSource(draft.source_path);
  if (source.error) errors.source_path = source.error;
  else if (isProtected(source.path)) errors.source_path = "sourceProtected";
  const target = targetKey(draft.target, draft.allow_external);
  if (target.error) errors.target = target.error;
  else if (source.path && target.key === source.path) errors.target = "targetSelf";
  if (!STATUS_CODES.includes(Number(draft.status_code))) errors.status_code = "status";
  return { source: source.path, errors };
}

// filters: { query: text, state: "all" | "active" | "inactive" }
export function filterRedirects(rows = [], { query = "", state = "all" } = {}) {
  const needle = query.trim().toLowerCase();
  return rows.filter(
    (row) =>
      (state === "all" || (state === "active" ? row.is_active : !row.is_active)) &&
      (!needle || [row.source_path, row.target, row.note].some((text) => (text || "").toLowerCase().includes(needle))),
  );
}

export function isFiltered(filters) {
  return Boolean(filters && (filters.state !== "all" || filters.query.trim()));
}

// The address a visitor would type for a stored source.
export function sourceUrl(path) {
  return `${SITE_URL}${path === "/" ? "/" : `${path}/`}`;
}

// What the form sends: only the editable fields, status as a number.
export function draftFrom(row) {
  if (!row) return { ...EMPTY_REDIRECT };
  return {
    source_path: row.source_path,
    target: row.target,
    status_code: Number(row.status_code) || 301,
    is_active: Boolean(row.is_active),
    allow_external: Boolean(row.allow_external),
    note: row.note || "",
  };
}

// The first message per field of a DRF error payload ({field: ["…"]}).
export function fieldMessages(errors = {}) {
  return Object.fromEntries(
    Object.entries(errors || {}).map(([field, value]) => [field, Array.isArray(value) ? String(value[0] ?? "") : String(value ?? "")]),
  );
}

// Badge tone for the "test a URL" outcome.
export function outcomeTone(outcome) {
  return { redirect: "ok", protected: "warn", inactive: "muted", invalid: "danger" }[outcome] || "muted";
}

// Rows of an import report with their error messages flattened, invalid first.
export function importRows(report) {
  const rows = (report?.rows || []).map((row) => ({ ...row, messages: Object.values(row.errors || {}) }));
  return rows.sort((a, b) => (b.messages.length > 0) - (a.messages.length > 0) || a.line - b.line);
}
