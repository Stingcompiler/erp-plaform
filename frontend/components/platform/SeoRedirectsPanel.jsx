"use client";

// The «التحويلات» / "Redirects" tab of /platform-seo: old public addresses
// sent to new ones (backend website/redirects.py). A table with search, an
// active switch and hit counts; an add/edit drawer that checks the rules as
// the team types; a "test a URL" box; and a CSV import with a dry run.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeftRight, ExternalLink, FileUp, Pencil, Plus, Search, Trash2 } from "lucide-react";

import { useI18n } from "../../app/providers/I18nProvider";
import { platformSeo } from "@/lib/api";
import { errorText } from "@/lib/errors";
import {
  EMPTY_REDIRECT, draftFrom, fieldMessages, filterRedirects, importRows, isFiltered, localErrors, outcomeTone, sourceUrl,
} from "@/lib/seoRedirects";
import { Badge, Button, Card, Field, Input, Select } from "@/components/ui/kit";
import { EmptyTableRow } from "@/components/ui/EmptyState";
import { useConfirm } from "@/components/ui/ConfirmDialog";
import Drawer from "@/components/ui/Drawer";
import { SkeletonCard } from "@/components/ui/Skeleton";

const NO_FILTERS = { query: "", state: "all" };
const TEXTAREA = "w-full rounded-control border border-line bg-surface px-3 py-2 font-mono text-xs text-ink outline-none focus:border-accent";
const SAMPLE_CSV = "source,target,status\n/old-page,/pricing/,301\n/en/old-page,/en/pricing/,301";

function ActiveSwitch({ checked, disabled, onChange, label }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={onChange}
      className="tap inline-flex shrink-0 items-center justify-center rounded-full disabled:opacity-50"
    >
      {/* The button is the (44 px on touch) hit area; the track keeps its size. */}
      <span className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${checked ? "bg-accent" : "bg-line"}`}>
        <span className={`inline-block h-5 w-5 rounded-full bg-white shadow transition-transform ${checked ? "translate-x-5 rtl:-translate-x-5" : "translate-x-0.5 rtl:-translate-x-0.5"}`} />
      </span>
    </button>
  );
}

export default function SeoRedirectsPanel({ canManage }) {
  const { t, language } = useI18n();
  const confirm = useConfirm();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [filters, setFilters] = useState(NO_FILTERS);
  const [busy, setBusy] = useState(null);

  const [editing, setEditing] = useState(null); // null | "new" | id
  const [draft, setDraft] = useState(EMPTY_REDIRECT);
  const [touched, setTouched] = useState({});
  const [serverErrors, setServerErrors] = useState({});
  const [checking, setChecking] = useState(false);
  const checkSeq = useRef(0);

  const [testInput, setTestInput] = useState("");
  const [testResult, setTestResult] = useState(null);

  const [importOpen, setImportOpen] = useState(false);
  const [importText, setImportText] = useState("");
  const [importFile, setImportFile] = useState(null);
  const [importReport, setImportReport] = useState(null);

  const load = useCallback(async () => {
    setError("");
    try {
      const response = await platformSeo.redirects();
      setRows(Array.isArray(response.data) ? response.data : response.data.results || []);
    } catch (requestError) {
      setError(errorText(requestError, t, "platformSeo.redirects.loadError"));
    } finally {
      setLoading(false);
    }
  }, [t]);
  useEffect(() => { load(); }, [load]);

  const flash = (message) => {
    setNotice(message);
    setTimeout(() => setNotice(""), 2500);
  };
  const fmt = (value) => new Date(value).toLocaleString(language === "ar" ? "ar" : "en", { dateStyle: "medium", timeStyle: "short" });
  const shown = useMemo(() => filterRedirects(rows, filters), [rows, filters]);
  const activeCount = rows.filter((row) => row.is_active).length;

  // --- Add / edit -----------------------------------------------------
  const local = useMemo(() => localErrors(draft), [draft]);
  const openEditor = (row) => {
    setEditing(row ? row.id : "new");
    setDraft(draftFrom(row));
    setTouched(row ? { source_path: true, target: true } : {});
    setServerErrors({});
  };
  const closeEditor = () => { setEditing(null); setServerErrors({}); };
  const setField = (key) => (event) => {
    const value = event.target.type === "checkbox" ? event.target.checked : event.target.value;
    setDraft((current) => ({ ...current, [key]: key === "status_code" ? Number(value) : value }));
    setTouched((current) => ({ ...current, [key]: true }));
  };

  // The server's rules (chains, loops, duplicates, app pages) once the
  // instant ones pass, a moment after the last keystroke.
  useEffect(() => {
    if (editing === null || !canManage) return undefined;
    if (Object.keys(local.errors).length || !draft.source_path.trim() || !draft.target.trim()) {
      setServerErrors({});
      return undefined;
    }
    const seq = ++checkSeq.current;
    const timer = setTimeout(async () => {
      setChecking(true);
      try {
        const body = { ...draft, ...(editing !== "new" ? { id: editing } : {}) };
        const response = await platformSeo.checkRedirect(body);
        if (seq === checkSeq.current) setServerErrors(fieldMessages(response.data.errors));
      } catch {
        if (seq === checkSeq.current) setServerErrors({});
      } finally {
        if (seq === checkSeq.current) setChecking(false);
      }
    }, 400);
    return () => clearTimeout(timer);
  }, [draft, editing, local, canManage]);

  const fieldError = (key) => {
    if (touched[key] && local.errors[key]) return t(`platformSeo.redirects.errors.${local.errors[key]}`);
    return serverErrors[key] || "";
  };
  const blocked = Object.keys(local.errors).length > 0 || Object.keys(serverErrors).length > 0;

  const save = async (event) => {
    event?.preventDefault();
    setTouched({ source_path: true, target: true, status_code: true });
    if (Object.keys(local.errors).length) return;
    setBusy("save");
    setError("");
    try {
      if (editing === "new") await platformSeo.createRedirect(draft);
      else await platformSeo.updateRedirect(editing, draft);
      closeEditor();
      flash(t("platformSeo.saved"));
      await load();
    } catch (requestError) {
      const data = requestError?.response?.data;
      if (requestError?.response?.status === 400 && data && typeof data === "object") setServerErrors(fieldMessages(data));
      else setError(errorText(requestError, t, "platformSeo.saveError"));
    } finally {
      setBusy(null);
    }
  };

  const toggle = async (row) => {
    setBusy(`toggle-${row.id}`);
    setError("");
    try {
      await platformSeo.updateRedirect(row.id, { is_active: !row.is_active });
      await load();
    } catch (requestError) {
      setError(errorText(requestError, t, "platformSeo.saveError"));
    } finally {
      setBusy(null);
    }
  };

  const remove = async (row) => {
    if (!(await confirm(t("platformSeo.redirects.confirmDelete", { path: row.source_path }), { tone: "danger" }))) return;
    setBusy(`delete-${row.id}`);
    setError("");
    try {
      await platformSeo.deleteRedirect(row.id);
      await load();
    } catch (requestError) {
      setError(errorText(requestError, t, "platformSeo.saveError"));
    } finally {
      setBusy(null);
    }
  };

  // --- Test a URL -----------------------------------------------------
  const runTest = async (event) => {
    event.preventDefault();
    if (!testInput.trim()) return;
    setBusy("test");
    try {
      const response = await platformSeo.testRedirect(testInput.trim());
      setTestResult(response.data);
    } catch (requestError) {
      setTestResult({ outcome: "invalid", message: errorText(requestError, t, "platformSeo.redirects.testError") });
    } finally {
      setBusy(null);
    }
  };

  // --- CSV import -----------------------------------------------------
  const openImport = () => { setImportOpen(true); setImportText(""); setImportFile(null); setImportReport(null); };
  const runImport = async (dryRun) => {
    setBusy(dryRun ? "preview" : "import");
    setError("");
    try {
      const response = await platformSeo.importRedirects({ file: importFile, csv: importText, dryRun });
      if (dryRun) setImportReport(response.data);
      else {
        setImportOpen(false);
        flash(t("platformSeo.redirects.imported", { count: response.data.created }));
        await load();
      }
    } catch (requestError) {
      const data = requestError?.response?.data;
      if (data?.rows) setImportReport(data);
      else {
        setImportReport(null);
        setError(errorText(requestError, t, "platformSeo.redirects.importError"));
      }
    } finally {
      setBusy(null);
    }
  };
  const previewRows = useMemo(() => importRows(importReport), [importReport]);
  const canImport = importReport && importReport.dry_run && importReport.invalid === 0 && importReport.total > 0;

  if (loading) return <SkeletonCard rows={5} />;

  const editor = (
    <form id="redirect-form" onSubmit={save} className="grid gap-4">
      <Field label={t("platformSeo.redirects.source")} hint={local.source && !fieldError("source_path") ? t("platformSeo.redirects.storedAs", { path: local.source }) : t("platformSeo.redirects.sourceHint")} error={fieldError("source_path")}>
        <Input dir="ltr" required maxLength={500} value={draft.source_path} onChange={setField("source_path")} placeholder="/old-page" autoFocus />
      </Field>
      <Field label={t("platformSeo.redirects.target")} hint={t("platformSeo.redirects.targetHint")} error={fieldError("target")}>
        <Input dir="ltr" required maxLength={500} value={draft.target} onChange={setField("target")} placeholder="/pricing/" />
      </Field>
      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" checked={draft.allow_external} onChange={setField("allow_external")} className="mt-0.5 h-4 w-4 accent-accent" />
        <span>{t("platformSeo.redirects.allowExternal")}<span className="block text-xs text-muted">{t("platformSeo.redirects.allowExternalHint")}</span></span>
      </label>
      <Field label={t("platformSeo.redirects.status")} error={fieldError("status_code")}>
        <Select value={draft.status_code} onChange={setField("status_code")}>
          <option value={301}>{t("platformSeo.redirects.status301")}</option>
          <option value={302}>{t("platformSeo.redirects.status302")}</option>
        </Select>
      </Field>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={draft.is_active} onChange={setField("is_active")} className="h-4 w-4 accent-accent" />
        {t("platformSeo.redirects.activeLabel")}
      </label>
      <Field label={t("platformSeo.redirects.note")}>
        <Input maxLength={255} value={draft.note} onChange={setField("note")} />
      </Field>
      <p className="text-xs text-muted" aria-live="polite">{checking ? t("platformSeo.redirects.checking") : ""}</p>
    </form>
  );

  return (
    <div>
      {error && <p role="alert" className="mb-4 rounded-control bg-danger/10 p-3 text-sm text-danger">{error}</p>}
      {notice && <p role="status" className="mb-4 rounded-control bg-ok/10 p-3 text-sm text-ok">{notice}</p>}

      {/* Test a URL. */}
      <Card className="mb-5 p-5">
        <h2 className="font-display font-semibold">{t("platformSeo.redirects.testTitle")}</h2>
        <p className="mt-1 text-sm text-muted">{t("platformSeo.redirects.testHint")}</p>
        <form onSubmit={runTest} className="mt-3 flex flex-col gap-2 sm:flex-row">
          <Input dir="ltr" value={testInput} onChange={(event) => setTestInput(event.target.value)} placeholder="/old-page?utm_source=x" aria-label={t("platformSeo.redirects.testTitle")} />
          <Button type="submit" variant="outline" className="shrink-0 whitespace-nowrap" disabled={busy === "test" || !testInput.trim()}>
            <Search size={15} />{t("platformSeo.redirects.testButton")}
          </Button>
        </form>
        {testResult && (
          <div className="mt-3 rounded-control border border-line bg-paper p-3 text-sm" aria-live="polite">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={outcomeTone(testResult.outcome)}>{t(`platformSeo.redirects.outcomes.${testResult.outcome}`)}</Badge>
              {testResult.path && <span className="font-mono text-xs" dir="ltr">{testResult.path}</span>}
            </div>
            {testResult.outcome === "redirect" && (
              <p className="mt-2 break-all">
                {t("platformSeo.redirects.testRedirect", { status: testResult.status_code })}{" "}
                <span className="font-mono text-xs" dir="ltr">{testResult.location}</span>
              </p>
            )}
            {testResult.outcome === "inactive" && <p className="mt-2">{t("platformSeo.redirects.testInactive", { target: testResult.redirect?.target })}</p>}
            {testResult.outcome === "none" && <p className="mt-2">{t("platformSeo.redirects.testNone")}</p>}
            {testResult.outcome === "protected" && <p className="mt-2">{t("platformSeo.redirects.testProtected")}</p>}
            {testResult.outcome === "invalid" && <p className="mt-2 text-danger">{testResult.message}</p>}
          </div>
        )}
      </Card>

      <Card className="p-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <h2 className="font-display font-semibold">{t("platformSeo.redirects.title")}</h2>
            <p className="mt-1 text-sm text-muted">{t("platformSeo.redirects.hint")}</p>
            <p className="mt-1 text-xs text-muted">{t("platformSeo.redirects.counts", { total: rows.length, active: activeCount })}</p>
          </div>
          {canManage && (
            <div className="flex shrink-0 flex-wrap gap-2">
              <Button variant="outline" className="whitespace-nowrap" onClick={openImport}><FileUp size={15} />{t("platformSeo.redirects.import")}</Button>
              <Button className="whitespace-nowrap" onClick={() => openEditor(null)}><Plus size={15} />{t("platformSeo.redirects.add")}</Button>
            </div>
          )}
        </div>

        <div className="mt-4 grid gap-2 sm:grid-cols-[2fr_1fr]">
          <Input type="search" value={filters.query} onChange={(event) => setFilters({ ...filters, query: event.target.value })} placeholder={t("platformSeo.redirects.search")} aria-label={t("platformSeo.redirects.search")} />
          <Select value={filters.state} onChange={(event) => setFilters({ ...filters, state: event.target.value })} aria-label={t("platformSeo.redirects.colActive")}>
            <option value="all">{t("platformSeo.redirects.stateAll")}</option>
            <option value="active">{t("platformSeo.redirects.stateActive")}</option>
            <option value="inactive">{t("platformSeo.redirects.stateInactive")}</option>
          </Select>
        </div>

        <div className="mt-3 overflow-x-auto">
          <table className="stack-sm w-full text-sm">
            <thead>
              <tr className="text-xs text-muted">
                <th className="px-2 py-2 text-start font-medium">{t("platformSeo.redirects.colSource")}</th>
                <th className="px-2 py-2 text-start font-medium">{t("platformSeo.redirects.colTarget")}</th>
                <th className="px-2 py-2 text-start font-medium">{t("platformSeo.redirects.colStatus")}</th>
                <th className="px-2 py-2 text-start font-medium">{t("platformSeo.redirects.colActive")}</th>
                <th className="px-2 py-2 text-start font-medium">{t("platformSeo.redirects.colHits")}</th>
                <th className="px-2 py-2" />
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <EmptyTableRow
                  cols={6}
                  icon={ArrowLeftRight}
                  title={t("platformSeo.redirects.emptyTitle")}
                  body={t("platformSeo.redirects.emptyBody")}
                  action={canManage && <Button onClick={() => openEditor(null)}><Plus size={15} />{t("platformSeo.redirects.add")}</Button>}
                />
              ) : shown.length === 0 ? (
                <EmptyTableRow cols={6} filtered={isFiltered(filters)} icon={ArrowLeftRight} title={t("platformSeo.redirects.emptyTitle")} onClearFilters={() => setFilters(NO_FILTERS)} />
              ) : shown.map((row) => (
                <tr key={row.id} className={`border-t border-line align-top ${row.is_active ? "" : "opacity-70"}`}>
                  <td className="px-2 py-2">
                    <a href={sourceUrl(row.source_path)} target="_blank" rel="noreferrer" dir="ltr" className="inline-flex items-center gap-1 break-all font-mono text-xs hover:text-accent" title={t("platformSeo.openPage")}>
                      {row.source_path}<ExternalLink size={11} className="shrink-0" />
                    </a>
                    {row.note && <div className="mt-0.5 text-xs text-muted" dir="auto">{row.note}</div>}
                  </td>
                  <td className="px-2 py-2">
                    <span className="break-all font-mono text-xs" dir="ltr">{row.target}</span>
                    {row.allow_external && <div className="mt-1"><Badge tone="warn">{t("platformSeo.redirects.external")}</Badge></div>}
                  </td>
                  <td className="px-2 py-2"><Badge tone={row.status_code === 301 ? "accent" : "muted"}>{row.status_code}</Badge></td>
                  <td className="px-2 py-2">
                    {canManage ? (
                      <ActiveSwitch checked={row.is_active} disabled={busy === `toggle-${row.id}`} onChange={() => toggle(row)} label={t("platformSeo.redirects.toggle", { path: row.source_path })} />
                    ) : (
                      <Badge tone={row.is_active ? "ok" : "muted"}>{t(row.is_active ? "platformSeo.redirects.stateActive" : "platformSeo.redirects.stateInactive")}</Badge>
                    )}
                  </td>
                  <td className="px-2 py-2">
                    <div className="tabular-nums">{row.hits.toLocaleString(language === "ar" ? "ar" : "en")}</div>
                    <div className="text-xs text-muted">{row.last_hit_at ? t("platformSeo.redirects.lastHit", { date: fmt(row.last_hit_at) }) : t("platformSeo.redirects.neverHit")}</div>
                  </td>
                  <td className="px-2 py-2">
                    {canManage && (
                      <div className="flex justify-end gap-1">
                        <Button variant="ghost" className="px-2" onClick={() => openEditor(row)} title={t("platformSeo.edit")} aria-label={t("platformSeo.edit")}><Pencil size={14} /></Button>
                        <Button variant="ghost" className="px-2 text-danger" disabled={busy === `delete-${row.id}`} onClick={() => remove(row)} title={t("platformSeo.delete")} aria-label={t("platformSeo.delete")}><Trash2 size={14} /></Button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Drawer
        open={editing !== null}
        onClose={closeEditor}
        title={editing === "new" ? t("platformSeo.redirects.addTitle") : t("platformSeo.redirects.editTitle")}
        footer={(
          <div className="flex flex-wrap gap-2">
            <Button type="submit" form="redirect-form" disabled={busy === "save" || blocked}>
              {busy === "save" ? t("platformSeo.saving") : t("platformSeo.redirects.save")}
            </Button>
            <Button type="button" variant="ghost" onClick={closeEditor}>{t("common.cancel")}</Button>
          </div>
        )}
      >
        {editor}
      </Drawer>

      <Drawer
        open={importOpen}
        onClose={() => setImportOpen(false)}
        wide
        title={t("platformSeo.redirects.importTitle")}
        footer={(
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" disabled={busy === "preview" || (!importText.trim() && !importFile)} onClick={() => runImport(true)}>
              {busy === "preview" ? t("platformSeo.redirects.previewing") : t("platformSeo.redirects.preview")}
            </Button>
            <Button disabled={!canImport || busy === "import"} onClick={() => runImport(false)}>
              {canImport ? t("platformSeo.redirects.importButton", { count: importReport.valid }) : t("platformSeo.redirects.importIdle")}
            </Button>
            <Button type="button" variant="ghost" onClick={() => setImportOpen(false)}>{t("common.cancel")}</Button>
          </div>
        )}
      >
        <p className="text-sm text-muted">{t("platformSeo.redirects.importHint")}</p>
        <pre className="mt-2 overflow-x-auto rounded-control bg-paper p-2 text-xs" dir="ltr">{SAMPLE_CSV}</pre>
        <div className="mt-4 grid gap-3">
          <Field label={t("platformSeo.redirects.importFile")}>
            <input
              type="file"
              accept=".csv,text/csv"
              onChange={(event) => { setImportFile(event.target.files?.[0] || null); setImportReport(null); }}
              className="block w-full text-sm file:me-3 file:rounded-control file:border file:border-line file:bg-surface file:px-3 file:py-1.5 file:text-sm"
            />
          </Field>
          {!importFile && (
            <Field label={t("platformSeo.redirects.importPaste")}>
              <textarea dir="ltr" rows={6} value={importText} onChange={(event) => { setImportText(event.target.value); setImportReport(null); }} className={TEXTAREA} placeholder={SAMPLE_CSV} />
            </Field>
          )}
        </div>
        {importReport && (
          <div className="mt-4">
            <div className="flex flex-wrap gap-2 text-sm">
              <Badge tone="muted">{t("platformSeo.redirects.importTotal", { count: importReport.total })}</Badge>
              <Badge tone="ok">{t("platformSeo.redirects.importValid", { count: importReport.valid })}</Badge>
              {importReport.invalid > 0 && <Badge tone="danger">{t("platformSeo.redirects.importInvalid", { count: importReport.invalid })}</Badge>}
            </div>
            {importReport.invalid > 0 && <p className="mt-2 text-sm text-danger">{t("platformSeo.redirects.importFix")}</p>}
            <div className="mt-3 overflow-x-auto">
              <table className="stack-sm w-full text-sm">
                <thead>
                  <tr className="text-xs text-muted">
                    <th className="px-2 py-2 text-start font-medium">{t("platformSeo.redirects.colLine")}</th>
                    <th className="px-2 py-2 text-start font-medium">{t("platformSeo.redirects.colSource")}</th>
                    <th className="px-2 py-2 text-start font-medium">{t("platformSeo.redirects.colTarget")}</th>
                    <th className="px-2 py-2 text-start font-medium">{t("platformSeo.redirects.colStatus")}</th>
                    <th className="px-2 py-2 text-start font-medium">{t("platformSeo.redirects.colResult")}</th>
                  </tr>
                </thead>
                <tbody>
                  {previewRows.map((row) => (
                    <tr key={row.line} className="border-t border-line align-top">
                      <td className="px-2 py-2 tabular-nums">{row.line}</td>
                      <td className="px-2 py-2 break-all font-mono text-xs" dir="ltr">{row.source_path || row.source}</td>
                      <td className="px-2 py-2 break-all font-mono text-xs" dir="ltr">{row.target}</td>
                      <td className="px-2 py-2">{String(row.status_code ?? "")}</td>
                      <td className="px-2 py-2">
                        {row.messages.length ? (
                          <ul className="space-y-1 text-danger">{row.messages.map((message) => <li key={message}>{message}</li>)}</ul>
                        ) : <Badge tone="ok">{t("platformSeo.redirects.rowOk")}</Badge>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
}
