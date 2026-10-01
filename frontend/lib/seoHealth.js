// Pure helpers for the «صحة SEO» tab of /platform-seo: the health report
// (GET /api/platform/seo/health/, backend website/seo_health.py) turned into
// filterable table rows, and the wording of each finding. No React here, so
// tests/seoHealth.test.mjs can exercise it directly.

export const SEVERITIES = ["error", "warn", "ok"];
const RANK = { error: 0, warn: 1, ok: 2 };

export function severityTone(severity) {
  return severity === "error" ? "danger" : severity === "warn" ? "warn" : "ok";
}

// One row per finding (page × issue), plus one "ok" row for a clean page, so
// filtering by issue or severity works on a flat list. Worst first, then by
// path, Arabic before English.
export function pageIssueRows(pages = []) {
  const rows = [];
  for (const page of pages) {
    const base = {
      path: page.path,
      language: page.language,
      url: page.url,
      urlPath: page.url_path,
      title: page.title,
      override: page.override || null,
    };
    if (!page.issues?.length) {
      rows.push({ ...base, key: `${page.url_path}|ok`, code: null, severity: "ok", params: {} });
      continue;
    }
    page.issues.forEach((issue, index) => {
      rows.push({ ...base, key: `${page.url_path}|${issue.code}|${index}`, code: issue.code, severity: issue.severity, params: issue.params || {} });
    });
  }
  return rows.sort(
    (a, b) => RANK[a.severity] - RANK[b.severity] || a.path.localeCompare(b.path) || a.language.localeCompare(b.language),
  );
}

// filters: { severity: "all"|…, language: "all"|"ar"|"en", code: "all"|code, query: text }
export function filterIssueRows(rows, { severity = "all", language = "all", code = "all", query = "" } = {}) {
  const needle = query.trim().toLowerCase();
  return rows.filter(
    (row) =>
      (severity === "all" || row.severity === severity) &&
      (language === "all" || row.language === language) &&
      (code === "all" || row.code === code) &&
      (!needle || row.path.toLowerCase().includes(needle) || (row.title || "").toLowerCase().includes(needle)),
  );
}

export function isFiltered(filters) {
  return Boolean(
    filters && (filters.severity !== "all" || filters.language !== "all" || filters.code !== "all" || filters.query.trim()),
  );
}

// The distinct issue codes present, for the filter menu (most common first).
export function issueCodes(rows) {
  const counts = new Map();
  for (const row of rows) if (row.code) counts.set(row.code, (counts.get(row.code) || 0) + 1);
  return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([code]) => code);
}

// What the override form starts with for a row: the existing override when
// one applies (edit it), otherwise a new one for exactly this path and
// language edition.
export function overrideDraftFor(row) {
  if (row.override) return { id: row.override.id, draft: null };
  return {
    id: null,
    draft: { path: row.path, language: row.language, title: "", description: "", noindex: false, canonical: "" },
  };
}

// Params a finding carries, made readable: lists joined, nothing undefined.
function vars(params = {}) {
  return Object.fromEntries(
    Object.entries(params).map(([key, value]) => [key, Array.isArray(value) ? value.join(", ") : String(value)]),
  );
}

// The short name of a finding, for the filter menu and the summary.
export function codeLabel(t, code) {
  const key = `platformSeo.health.codes.${code}`;
  const text = t(key);
  return text === key ? code : text;
}

// "platformSeo.health.issues.<code>" with its params; an unknown code (a
// newer backend) falls back to the code itself rather than a raw key.
export function issueText(t, issue) {
  if (!issue?.code) return t("platformSeo.health.noIssues");
  const key = `platformSeo.health.issues.${issue.code}`;
  const text = t(key, vars(issue.params));
  return text === key ? issue.code : text;
}
