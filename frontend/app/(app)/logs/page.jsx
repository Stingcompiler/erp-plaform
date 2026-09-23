"use client";

import { useCallback, useEffect, useState } from "react";
import { Lock, Search } from "lucide-react";

import { logs as logsApi, users as usersApi } from "@/lib/api";
import { useAuth } from "../../providers/AuthProvider";
import { useI18n } from "../../providers/I18nProvider";
import { translateRole } from "@/lib/i18n";
import { Badge, Button, Card, Field, Input, PageHeader, Select } from "@/components/ui/kit";
import { SkeletonRows } from "@/components/ui/Skeleton";

const ACTION_TONE = {
  login: "accent",
  logout: "muted",
  create: "ok",
  update: "warn",
  delete: "danger",
  archive: "warn",
  unarchive: "ok",
  export: "accent",
  view: "muted",
  approve: "ok",
};
// Only the actions worth filtering by are offered in the dropdown; the rest
// (view, reminder scans) still render in the table but would just clutter the
// filter.
const ACTION_KEY = {
  create: "logs.actionCreate",
  update: "logs.actionUpdate",
  delete: "logs.actionDelete",
  archive: "logs.actionArchive",
  unarchive: "logs.actionUnarchive",
  approve: "logs.actionApprove",
  export: "logs.actionExport",
  login: "logs.actionLogin",
  logout: "logs.actionLogout",
};

// Turns the raw metadata each action records into one plain-language line, so
// an admin reads what happened instead of a JSON blob. Falls back to the
// before→after diff for ordinary updates, and to nothing when there's no
// operational detail to show.
function Details({ log }) {
  const { t } = useI18n();
  const m = log.metadata || {};

  if (typeof m.count === "number" && log.action === "export") {
    return <span className="text-ink">{t("logs.exportedRows", { count: m.count })}</span>;
  }
  if (m.verified) {
    return <span className="text-ok">{t("logs.verifiedBy")}</span>;
  }
  if (Array.isArray(m.fields) && m.fields.length) {
    return (
      <span className="text-ink">
        {t("logs.fieldsChanged", { fields: m.fields.join("، ") })}
      </span>
    );
  }
  if (Array.isArray(m.disposition)) {
    return (
      <span className="text-ink">
        {t("logs.dispositioned", { count: m.disposition.length })}
      </span>
    );
  }
  if (m.converted_from_lead) {
    return (
      <span className="text-ink">
        {t("logs.convertedFromLead", { id: m.converted_from_lead })}
      </span>
    );
  }
  if (m.invoice_format) {
    return (
      <span className="text-ink">
        {t("logs.invoiceFormat", { value: m.invoice_format })}
      </span>
    );
  }
  if (typeof m.status === "string") {
    return <span className="text-ink">{t("logs.statusSet", { value: m.status })}</span>;
  }

  const changes = m.changes;
  if (changes && Object.keys(changes).length > 0) {
    return (
      <div className="space-y-0.5">
        {Object.entries(changes).map(([field, v]) => (
          <div key={field} className="text-xs">
            <span className="font-medium text-ink">{field}: </span>
            <span className="text-danger line-through">{String(v.before ?? "")}</span>
            <span className="text-muted"> → </span>
            <span className="text-ok">{String(v.after ?? "")}</span>
          </div>
        ))}
      </div>
    );
  }

  // Anything else with simple scalar values (backup kind, invoice number/total)
  // is shown as compact key: value pairs rather than a bare dash — the point of
  // this column is that no recorded detail stays hidden. Nested objects are
  // skipped; a recognised shape above would have handled those.
  const scalars = Object.entries(m).filter(
    ([, v]) => v !== null && typeof v !== "object",
  );
  if (scalars.length) {
    return (
      <div className="space-y-0.5 text-xs text-ink">
        {scalars.map(([k, v]) => (
          <div key={k}>
            <span className="text-muted">{k}: </span>
            {String(v)}
          </div>
        ))}
      </div>
    );
  }
  return <span className="text-muted">{t("logs.noChanges")}</span>;
}

// Who acted: name over role, with the email kept as a subtle secondary line so
// two people who share a first name are still distinguishable.
function Person({ log }) {
  const { t } = useI18n();
  if (!log.user_email && !log.user_name) {
    return <span className="text-muted">{t("logs.noUser")}</span>;
  }
  return (
    <div className="min-w-0">
      <div className="truncate font-medium text-ink">
        {log.user_name || log.user_email}
      </div>
      {log.user_role && (
        <div className="truncate text-xs text-muted">
          {translateRole(log.user_role, t)}
        </div>
      )}
      {log.user_name && log.user_email && (
        <div className="truncate text-xs text-muted/70">{log.user_email}</div>
      )}
    </div>
  );
}

export default function LogsPage() {
  const { canWrite } = useAuth();
  const { t, language } = useI18n();
  const allowed = canWrite("settings");

  const [rows, setRows] = useState([]);
  const [count, setCount] = useState(0);
  const [people, setPeople] = useState([]);
  const [loading, setLoading] = useState(true);
  const [denied, setDenied] = useState(false);
  const [filters, setFilters] = useState({
    search: "",
    action: "",
    user: "",
    start: "",
    end: "",
  });

  const load = useCallback(() => {
    setLoading(true);
    const params = Object.fromEntries(
      Object.entries(filters).filter(([, v]) => v !== "")
    );
    logsApi
      .list({ ...params, page: 1 })
      .then((r) => {
        setRows(r.data.results);
        setCount(r.data.count);
        setDenied(false);
      })
      .catch((err) => {
        if (err?.response?.status === 403) setDenied(true);
        setRows([]);
        setCount(0);
      })
      .finally(() => setLoading(false));
  }, [filters]);

  useEffect(() => {
    if (allowed) load();
    else setLoading(false);
  }, [allowed, load]);

  useEffect(() => {
    if (!allowed) return;
    usersApi
      .list({ page: 1 })
      .then((r) => setPeople(r.data.results))
      .catch(() => setPeople([]));
  }, [allowed]);

  const set = (k, v) => setFilters((f) => ({ ...f, [k]: v }));
  const dt = (d) =>
    d ? new Date(d).toLocaleString(language === "ar" ? "ar" : "en") : "—";

  if (!allowed || denied) {
    return (
      <div className="mx-auto mt-16 max-w-md rounded-card border border-line bg-surface p-8 text-center">
        <Lock className="mx-auto text-muted" />
        <h1 className="mt-3 font-display text-xl font-semibold">
          {t("shell.noAccessTitle")}
        </h1>
        <p className="mt-1 text-muted">{t("logs.noAccess")}</p>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title={t("logs.title")}
        subtitle={t("logs.subtitle")}
        actions={
          <span className="tabular text-sm text-muted">
            {t("logs.showing", { count })}
          </span>
        }
      />

      {/* Filters */}
      <Card className="mb-4 p-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <div className="lg:col-span-2">
            <Field label={t("common.search")}>
              <div className="relative">
                <Search
                  size={15}
                  className="pointer-events-none absolute inset-y-0 start-3 my-auto text-muted"
                />
                <Input
                  className="ps-9"
                  placeholder={t("logs.searchPlaceholder")}
                  value={filters.search}
                  onChange={(e) => set("search", e.target.value)}
                />
              </div>
            </Field>
          </div>
          <Field label={t("logs.action")}>
            <Select value={filters.action} onChange={(e) => set("action", e.target.value)}>
              <option value="">{t("logs.allActions")}</option>
              {Object.entries(ACTION_KEY).map(([val, key]) => (
                <option key={val} value={val}>{t(key)}</option>
              ))}
            </Select>
          </Field>
          <Field label={t("logs.user")}>
            <Select value={filters.user} onChange={(e) => set("user", e.target.value)}>
              <option value="">{t("logs.allUsers")}</option>
              {people.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.full_name ? `${p.full_name} — ${p.email}` : p.email}
                </option>
              ))}
            </Select>
          </Field>
          <div className="grid grid-cols-2 gap-2">
            <Field label={t("logs.from")}>
              <Input type="date" value={filters.start} onChange={(e) => set("start", e.target.value)} />
            </Field>
            <Field label={t("logs.to")}>
              <Input type="date" value={filters.end} onChange={(e) => set("end", e.target.value)} />
            </Field>
          </div>
        </div>
        <div className="mt-3 flex justify-end">
          <Button
            variant="outline"
            onClick={() => setFilters({ search: "", action: "", user: "", start: "", end: "" })}
          >
            {t("logs.clear")}
          </Button>
        </div>
      </Card>

      {loading && <SkeletonRows />}

      {!loading && rows.length === 0 && (
        <Card className="p-8 text-center text-muted">{t("logs.noLogs")}</Card>
      )}

      {!loading && rows.length > 0 && (
        <Card>
          <div className="overflow-x-auto">
            <table className="stack-sm w-full text-sm">
              <thead>
                <tr className="border-b border-line text-xs uppercase tracking-wide text-muted">
                  <th className="px-4 py-3 text-start font-medium">{t("logs.when")}</th>
                  <th className="px-4 py-3 text-start font-medium">{t("logs.user")}</th>
                  <th className="px-4 py-3 text-start font-medium">{t("logs.action")}</th>
                  <th className="px-4 py-3 text-start font-medium">{t("logs.entity")}</th>
                  <th className="px-4 py-3 text-start font-medium">{t("logs.details")}</th>
                  <th className="px-4 py-3 text-start font-medium">{t("logs.ipAddress")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-b border-line last:border-0 align-top">
                    <td className="tabular whitespace-nowrap px-4 py-3 text-muted">{dt(r.created_at)}</td>
                    <td className="px-4 py-3"><Person log={r} /></td>
                    <td className="px-4 py-3">
                      <Badge tone={ACTION_TONE[r.action] || "muted"}>
                        {ACTION_KEY[r.action] ? t(ACTION_KEY[r.action]) : r.action}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 text-muted">
                      {r.entity_type ? `${r.entity_type}${r.entity_id ? ` #${r.entity_id}` : ""}` : "—"}
                    </td>
                    <td className="px-4 py-3"><Details log={r} /></td>
                    <td className="tabular px-4 py-3 text-xs text-muted">{r.ip_address || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
