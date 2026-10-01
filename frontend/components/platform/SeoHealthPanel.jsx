"use client";

// The «صحة SEO» tab of /platform-seo: what search engines are given, checked
// (backend website/seo_health.py). Read-only; a manager can recompute it and
// jump from a finding to an override prefilled with that page and language.

import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowLeftRight, Building2, ExternalLink, FileSearch, Map as MapIcon, Pencil, Plus, RefreshCw, Settings2 } from "lucide-react";

import { useI18n } from "../../app/providers/I18nProvider";
import { platformSeo } from "@/lib/api";
import { errorText } from "@/lib/errors";
import {
  SEVERITIES, codeLabel, filterIssueRows, isFiltered, issueCodes, issueText, pageIssueRows, severityTone,
} from "@/lib/seoHealth";
import { Badge, Button, Card, Input, Select } from "@/components/ui/kit";
import { EmptyState, EmptyTableRow } from "@/components/ui/EmptyState";
import { SkeletonCard } from "@/components/ui/Skeleton";

const NO_FILTERS = { severity: "all", language: "all", code: "all", query: "" };
const CHIP = "tap inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm font-medium transition-colors";
const CHIP_TONES = {
  error: "border-danger/30 bg-danger/10 text-danger",
  warn: "border-warn/30 bg-warn/10 text-warn",
  ok: "border-ok/30 bg-ok/10 text-ok",
};

function SeverityBadge({ severity, t }) {
  return <Badge tone={severityTone(severity)}>{t(`platformSeo.health.severity.${severity}`)}</Badge>;
}

function Section({ icon: Icon, title, hint, children, actions }) {
  return (
    <Card className="mb-5 p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-accent/10 text-accent"><Icon size={20} /></span>
          <div className="min-w-0">
            <h2 className="font-display font-semibold">{title}</h2>
            {hint && <p className="mt-1 text-sm text-muted">{hint}</p>}
          </div>
        </div>
        {actions}
      </div>
      {children}
    </Card>
  );
}

function IssueList({ issues, t }) {
  if (!issues?.length) return <span className="text-ok">{t("platformSeo.health.noIssues")}</span>;
  return (
    <ul className="space-y-1">
      {issues.map((issue, index) => (
        <li key={`${issue.code}-${index}`} className="flex items-start gap-2">
          <SeverityBadge severity={issue.severity} t={t} />
          <span className="min-w-0 break-words">{issueText(t, issue)}</span>
        </li>
      ))}
    </ul>
  );
}

export default function SeoHealthPanel({ canManage, onOverride, onRedirects }) {
  const { t, language } = useI18n();
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [filters, setFilters] = useState(NO_FILTERS);

  const load = useCallback(async (refresh = false) => {
    if (refresh) setRefreshing(true); else setLoading(true);
    setError("");
    try {
      const response = await platformSeo.health(refresh);
      setReport(response.data);
    } catch (requestError) {
      setError(errorText(requestError, t, "platformSeo.health.loadError"));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [t]);
  useEffect(() => { load(); }, [load]);

  const rows = useMemo(() => pageIssueRows(report?.pages), [report]);
  const codes = useMemo(() => issueCodes(rows), [rows]);
  const shown = useMemo(() => filterIssueRows(rows, filters), [rows, filters]);
  const companies = useMemo(
    () => [...(report?.companies || [])].sort((a, b) => SEVERITIES.indexOf(a.severity) - SEVERITIES.indexOf(b.severity)),
    [report],
  );
  const flaggedRedirects = useMemo(() => (report?.redirects || []).filter((row) => row.issues.length > 0), [report]);
  const setFilter = (key) => (event) => setFilters({ ...filters, [key]: event.target.value });
  const fmt = (value) => new Date(value).toLocaleString(language === "ar" ? "ar" : "en", { dateStyle: "medium", timeStyle: "short" });

  if (loading) return <SkeletonCard rows={6} />;
  if (!report) {
    return (
      <Card className="p-5">
        {error && <p role="alert" className="mb-4 rounded-control bg-danger/10 p-3 text-sm text-danger">{error}</p>}
        <EmptyState icon={FileSearch} title={t("platformSeo.health.loadError")} action={<Button variant="outline" onClick={() => load()}>{t("platformSeo.health.retry")}</Button>} />
      </Card>
    );
  }

  const { summary, sitemap } = report;
  const openLink = (url) => (
    <a href={url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 hover:text-accent" title={t("platformSeo.openPage")}>
      <ExternalLink size={13} /><span className="sr-only">{t("platformSeo.openPage")}</span>
    </a>
  );

  return (
    <div>
      {error && <p role="alert" className="mb-4 rounded-control bg-danger/10 p-3 text-sm text-danger">{error}</p>}

      {/* Summary: every checked item by its worst finding, and the commonest findings. */}
      <Card className="mb-5 p-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <h2 className="font-display font-semibold">{t("platformSeo.health.summaryTitle")}</h2>
            <p className="mt-1 text-sm text-muted">
              {t("platformSeo.health.summaryHint", { total: summary.total })}{" "}
              {t(report.cached ? "platformSeo.health.cachedAt" : "platformSeo.health.checkedAt", { date: fmt(report.generated_at) })}
            </p>
          </div>
          {canManage && (
            <Button variant="outline" className="shrink-0 whitespace-nowrap" disabled={refreshing} onClick={() => load(true)}>
              <RefreshCw size={15} className={refreshing ? "motion-safe:animate-spin" : ""} />
              {refreshing ? t("platformSeo.health.refreshing") : t("platformSeo.health.refresh")}
            </Button>
          )}
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          {SEVERITIES.map((severity) => (
            <button
              key={severity}
              type="button"
              aria-pressed={filters.severity === severity}
              onClick={() => setFilters({ ...filters, severity: filters.severity === severity ? "all" : severity })}
              className={`${CHIP} ${CHIP_TONES[severity]} ${filters.severity === severity ? "ring-2 ring-accent/40" : ""}`}
            >
              <span className="tabular-nums">{summary[severity]}</span>
              {t(`platformSeo.health.severity.${severity}`)}
            </button>
          ))}
        </div>
        {summary.issues.length > 0 && (
          <div className="mt-4">
            <p className="text-xs font-medium text-muted">{t("platformSeo.health.topIssues")}</p>
            <ul className="mt-2 grid gap-1.5 text-sm sm:grid-cols-2">
              {summary.issues.slice(0, 6).map((item) => (
                <li key={`${item.code}-${item.severity}`} className="flex items-center gap-2">
                  <SeverityBadge severity={item.severity} t={t} />
                  <span className="min-w-0 truncate">{codeLabel(t, item.code)}</span>
                  <span className="ms-auto shrink-0 tabular-nums text-muted">×{item.count}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </Card>

      {/* Exported marketing pages, one row per finding. */}
      <Section icon={FileSearch} title={t("platformSeo.health.pagesTitle")} hint={t("platformSeo.health.pagesHint", { count: report.pages.length, ...Object.fromEntries(Object.entries(report.limits).map(([key, [min, max]]) => [key, `${min}–${max}`])) })}>
        <div className="mt-4 grid gap-2 sm:grid-cols-[2fr_1fr_1fr_2fr]">
          <Input type="search" value={filters.query} onChange={setFilter("query")} placeholder={t("platformSeo.health.searchPlaceholder")} aria-label={t("platformSeo.health.searchPlaceholder")} />
          <Select value={filters.severity} onChange={setFilter("severity")} aria-label={t("platformSeo.health.colSeverity")}>
            <option value="all">{t("platformSeo.health.allSeverities")}</option>
            {SEVERITIES.map((severity) => <option key={severity} value={severity}>{t(`platformSeo.health.severity.${severity}`)}</option>)}
          </Select>
          <Select value={filters.language} onChange={setFilter("language")} aria-label={t("platformSeo.health.colLanguage")}>
            <option value="all">{t("platformSeo.health.allLanguages")}</option>
            <option value="ar">{t("platformSeo.health.languages.ar")}</option>
            <option value="en">{t("platformSeo.health.languages.en")}</option>
          </Select>
          <Select value={filters.code} onChange={setFilter("code")} aria-label={t("platformSeo.health.colIssue")}>
            <option value="all">{t("platformSeo.health.allIssues")}</option>
            {codes.map((code) => <option key={code} value={code}>{codeLabel(t, code)}</option>)}
          </Select>
        </div>
        <div className="mt-3 overflow-x-auto">
          <table className="stack-sm w-full text-sm">
            <thead>
              <tr className="text-xs text-muted">
                <th className="px-2 py-2 text-start font-medium">{t("platformSeo.health.colPage")}</th>
                <th className="px-2 py-2 text-start font-medium">{t("platformSeo.health.colLanguage")}</th>
                <th className="px-2 py-2 text-start font-medium">{t("platformSeo.health.colIssue")}</th>
                <th className="px-2 py-2 text-start font-medium">{t("platformSeo.health.colSeverity")}</th>
                <th className="px-2 py-2" />
              </tr>
            </thead>
            <tbody>
              {report.pages.length === 0 ? (
                <EmptyTableRow cols={5} icon={FileSearch} title={t("platformSeo.health.noPagesTitle")} body={t("platformSeo.health.noPagesBody")} />
              ) : shown.length === 0 ? (
                <EmptyTableRow cols={5} filtered={isFiltered(filters)} icon={FileSearch} title={t("platformSeo.health.noPagesTitle")} onClearFilters={() => setFilters(NO_FILTERS)} />
              ) : shown.map((row) => (
                <tr key={row.key} className="border-t border-line align-top">
                  <td className="px-2 py-2">
                    <div className="min-w-0">
                      <div className="font-mono text-xs" dir="ltr">{row.urlPath}</div>
                      {row.title && <div className="mt-0.5 line-clamp-1 text-xs text-muted" dir="auto">{row.title}</div>}
                      {row.override && <Badge tone="accent">{t("platformSeo.health.hasOverride")}</Badge>}
                    </div>
                  </td>
                  <td className="whitespace-nowrap px-2 py-2">{t(`platformSeo.health.languages.${row.language}`)}</td>
                  <td className="px-2 py-2"><span className="break-words">{issueText(t, row)}</span></td>
                  <td className="px-2 py-2"><SeverityBadge severity={row.severity} t={t} /></td>
                  <td className="px-2 py-2">
                    <div className="flex items-center justify-end gap-2">
                      {openLink(row.url)}
                      {canManage && (
                        <Button variant="ghost" className="whitespace-nowrap px-2 text-xs" onClick={() => onOverride(row)}>
                          {row.override ? <Pencil size={13} /> : <Plus size={13} />}
                          {row.override ? t("platformSeo.health.editOverride") : t("platformSeo.health.createOverride")}
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      {/* The marketing sitemap against the export. */}
      <Section icon={MapIcon} title={t("platformSeo.health.sitemapTitle")} hint={t("platformSeo.health.sitemapHint")} actions={<SeverityBadge severity={sitemap.severity} t={t} />}>
        <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-3">
          <div className="rounded-control border border-line p-3">
            <dt className="text-xs text-muted">{t("platformSeo.health.sitemapUrls")}</dt>
            <dd className="mt-1 font-display text-xl font-semibold tabular-nums">{sitemap.url_count}</dd>
          </div>
          <div className="rounded-control border border-line p-3">
            <dt className="text-xs text-muted">{t("platformSeo.health.notInSitemap")}</dt>
            <dd className="mt-1 font-display text-xl font-semibold tabular-nums">{sitemap.missing_from_sitemap.length}</dd>
          </div>
          <div className="rounded-control border border-line p-3">
            <dt className="text-xs text-muted">{t("platformSeo.health.notInExport")}</dt>
            <dd className="mt-1 font-display text-xl font-semibold tabular-nums">{sitemap.missing_from_export.length}</dd>
          </div>
        </dl>
        {[["notInSitemap", sitemap.missing_from_sitemap], ["notInExport", sitemap.missing_from_export]].map(([label, paths]) =>
          paths.length > 0 && (
            <div key={label} className="mt-3">
              <p className="text-xs font-medium text-muted">{t(`platformSeo.health.${label}`)}</p>
              <ul className="mt-1 flex flex-wrap gap-1.5" dir="ltr">
                {paths.map((path) => <li key={path} className="rounded bg-paper px-2 py-0.5 font-mono text-xs">{path}</li>)}
              </ul>
            </div>
          ),
        )}
        <div className="mt-3 text-sm"><IssueList issues={sitemap.issues} t={t} /></div>
        <p className="mt-3 text-xs text-muted">{t("platformSeo.health.companySitemapNote")}</p>
      </Section>

      {/* Published company pages (/s/<slug>/). */}
      <Section icon={Building2} title={t("platformSeo.health.companiesTitle")} hint={t("platformSeo.health.companiesHint")}>
        <div className="mt-4 overflow-x-auto">
          <table className="stack-sm w-full text-sm">
            <thead>
              <tr className="text-xs text-muted">
                <th className="px-2 py-2 text-start font-medium">{t("platformSeo.health.colCompany")}</th>
                <th className="px-2 py-2 text-start font-medium">{t("platformSeo.health.colStatus")}</th>
                <th className="px-2 py-2 text-start font-medium">{t("platformSeo.health.colIssue")}</th>
                <th className="px-2 py-2 text-start font-medium">{t("platformSeo.health.colSeverity")}</th>
                <th className="px-2 py-2" />
              </tr>
            </thead>
            <tbody>
              {companies.length === 0 ? (
                <EmptyTableRow cols={5} icon={Building2} title={t("platformSeo.health.noCompaniesTitle")} body={t("platformSeo.health.noCompaniesBody")} />
              ) : companies.map((row) => (
                <tr key={row.company_id} className="border-t border-line align-top">
                  <td className="px-2 py-2">
                    <div className="min-w-0">
                      <div className="font-medium" dir="auto">{row.name}</div>
                      <div className="font-mono text-xs text-muted" dir="ltr">{row.path}/</div>
                    </div>
                  </td>
                  <td className="px-2 py-2">
                    <div className="flex flex-wrap justify-end gap-1 sm:justify-start">
                      <Badge tone={row.in_directory ? "ok" : "warn"}>{t(row.in_directory ? "platformSeo.health.inDirectory" : "platformSeo.health.notInDirectory")}</Badge>
                      {row.is_demo && <Badge tone="muted">{t("platformSeo.health.demo")}</Badge>}
                    </div>
                  </td>
                  <td className="px-2 py-2 text-sm"><IssueList issues={row.issues} t={t} /></td>
                  <td className="px-2 py-2"><SeverityBadge severity={row.severity} t={t} /></td>
                  <td className="px-2 py-2">
                    <div className="flex items-center justify-end gap-2">
                      {openLink(row.url)}
                      {canManage && (
                        <Button variant="ghost" className="whitespace-nowrap px-2 text-xs" onClick={() => onOverride({ path: row.path, language: "both", override: null })}>
                          <Plus size={13} />{t("platformSeo.health.createOverride")}
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      {/* Redirects: old paths still in a sitemap, new addresses with no page. */}
      {(report.redirects || []).length > 0 && (
        <Section
          icon={ArrowLeftRight}
          title={t("platformSeo.health.redirectsTitle")}
          hint={t("platformSeo.health.redirectsHint", { count: report.redirects.length })}
          actions={onRedirects && <Button variant="outline" className="shrink-0 whitespace-nowrap" onClick={onRedirects}>{t("platformSeo.health.openRedirects")}</Button>}
        >
          {flaggedRedirects.length === 0 ? (
            <p className="mt-4 text-sm text-ok">{t("platformSeo.health.redirectsOk")}</p>
          ) : (
            <div className="mt-4 overflow-x-auto">
              <table className="stack-sm w-full text-sm">
                <thead>
                  <tr className="text-xs text-muted">
                    <th className="px-2 py-2 text-start font-medium">{t("platformSeo.health.colRedirect")}</th>
                    <th className="px-2 py-2 text-start font-medium">{t("platformSeo.health.colIssue")}</th>
                    <th className="px-2 py-2 text-start font-medium">{t("platformSeo.health.colSeverity")}</th>
                  </tr>
                </thead>
                <tbody>
                  {flaggedRedirects.map((row) => (
                    <tr key={row.id} className="border-t border-line align-top">
                      <td className="px-2 py-2">
                        <div className="break-all font-mono text-xs" dir="ltr">{row.source_path} → {row.target}</div>
                      </td>
                      <td className="px-2 py-2 text-sm"><IssueList issues={row.issues} t={t} /></td>
                      <td className="px-2 py-2"><SeverityBadge severity={row.severity} t={t} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>
      )}

      {/* Site-wide settings. */}
      <Section icon={Settings2} title={t("platformSeo.health.settingsTitle")} hint={t("platformSeo.health.settingsHint")}>
        <ul className="mt-4 divide-y divide-line text-sm">
          {report.settings.map((check) => (
            <li key={check.code} className="flex flex-col gap-1 py-2 sm:flex-row sm:items-start sm:gap-4">
              <span className="font-medium sm:w-56 sm:shrink-0">{t(`platformSeo.health.checks.${check.code}`)}</span>
              <div className="min-w-0 flex-1">
                {check.issues.length ? <IssueList issues={check.issues} t={t} /> : <SeverityBadge severity="ok" t={t} />}
              </div>
            </li>
          ))}
        </ul>
      </Section>
    </div>
  );
}
