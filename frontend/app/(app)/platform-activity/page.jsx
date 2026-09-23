"use client";

// The platform team's audit trail as a table: when, what, which area, who,
// from where. Filters by member, entity, action, date range and free text;
// pages through the API's pagination with "load more".
import { useCallback, useEffect, useState } from "react";
import { Lock, ScrollText } from "lucide-react";

import { useAuth } from "../../providers/AuthProvider";
import { useI18n } from "../../providers/I18nProvider";
import { platformTeam } from "@/lib/api";
import { activityKind, describeActivity } from "@/lib/platformActivity";
import { Badge, Button, Card, Field, Input, PageHeader, Select } from "@/components/ui/kit";
import { SkeletonRows } from "@/components/ui/Skeleton";

const EMPTY = { user: "", entity_type: "", action: "", start: "", end: "", search: "" };

export default function PlatformActivityPage() {
  const { user, can } = useAuth();
  const { t, language } = useI18n();
  const canView = can("platform.team.view");
  const [rows, setRows] = useState([]);
  const [count, setCount] = useState(0);
  const [next, setNext] = useState(null);
  const [members, setMembers] = useState([]);
  const [facets, setFacets] = useState({ actions: [], entity_types: [] });
  const [draft, setDraft] = useState(EMPTY);
  const [filters, setFilters] = useState(EMPTY);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const roleLabel = (name) => {
    if (!name) return "";
    const label = t(`platformTeam.roles.${name}`);
    return label.startsWith("platformTeam.") ? name : label;
  };
  const fmt = (value) =>
    new Date(value).toLocaleString(language === "ar" ? "ar" : "en", { dateStyle: "medium", timeStyle: "short" });

  const load = useCallback(async (params, append = false, url = null) => {
    setLoading(true);
    setError("");
    try {
      const response = url
        ? await platformTeam.activity({ ...params, page: new URL(url).searchParams.get("page") })
        : await platformTeam.activity(params);
      const data = response.data;
      const list = Array.isArray(data) ? data : data.results || [];
      setRows((current) => (append ? [...current, ...list] : list));
      setCount(Array.isArray(data) ? list.length : data.count ?? list.length);
      setNext(Array.isArray(data) ? null : data.next || null);
    } catch {
      setError(t("platformActivity.loadError"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    if (!canView) { setLoading(false); return; }
    const active = Object.fromEntries(Object.entries(filters).filter(([, v]) => v));
    load(active);
  }, [canView, filters, load]);

  useEffect(() => {
    if (!canView) return;
    platformTeam.list().then((r) => setMembers(r.data)).catch(() => {});
    platformTeam.activityFacets().then((r) => setFacets(r.data)).catch(() => {});
  }, [canView]);

  if (!canView) {
    return (
      <Card className="mx-auto mt-16 max-w-md p-8 text-center">
        <Lock className="mx-auto text-muted" />
        <p className="mt-3 text-muted">{t("platformActivity.noAccess")}</p>
      </Card>
    );
  }

  const set = (key) => (event) => setDraft((d) => ({ ...d, [key]: event.target.value }));
  const apply = (event) => { event.preventDefault(); setFilters(draft); };
  const clear = () => { setDraft(EMPTY); setFilters(EMPTY); };
  const loadMore = () => {
    const active = Object.fromEntries(Object.entries(filters).filter(([, v]) => v));
    load(active, true, next);
  };

  return (
    <div>
      <PageHeader
        title={t("platformActivity.title")}
        subtitle={t("platformActivity.subtitle")}
        actions={<Badge tone="accent"><ScrollText size={14} /> {t("platformActivity.count", { count })}</Badge>}
      />
      {error && <p role="alert" className="mb-4 rounded-control bg-danger/10 p-3 text-sm text-danger">{error}</p>}

      <Card className="mb-5 p-4">
        <form onSubmit={apply} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
          <Field label={t("platformActivity.filterMember")}>
            <Select value={draft.user} onChange={set("user")}>
              <option value="">{t("platformActivity.allMembers")}</option>
              {members.map((m) => <option key={m.id} value={m.id}>{m.full_name || m.email}</option>)}
            </Select>
          </Field>
          <Field label={t("platformActivity.filterKind")}>
            <Select value={draft.entity_type} onChange={set("entity_type")}>
              <option value="">{t("platformActivity.allKinds")}</option>
              {facets.entity_types.filter(Boolean).map((k) => <option key={k} value={k}>{activityKind({ entity_type: k }, t)} · {k}</option>)}
            </Select>
          </Field>
          <Field label={t("platformActivity.filterAction")}>
            <Select value={draft.action} onChange={set("action")}>
              <option value="">{t("platformActivity.allActions")}</option>
              {facets.actions.map((a) => <option key={a} value={a}>{a}</option>)}
            </Select>
          </Field>
          <Field label={t("platformActivity.from")}><Input type="date" value={draft.start} onChange={set("start")} /></Field>
          <Field label={t("platformActivity.to")}><Input type="date" value={draft.end} onChange={set("end")} /></Field>
          <Field label={t("platformActivity.search")}><Input value={draft.search} onChange={set("search")} /></Field>
          <div className="flex items-end gap-2 sm:col-span-2 lg:col-span-6">
            <Button type="submit">{t("platformActivity.apply")}</Button>
            <Button type="button" variant="ghost" onClick={clear}>{t("platformActivity.clear")}</Button>
          </div>
        </form>
      </Card>

      <Card className="overflow-hidden">
        {loading && rows.length === 0 ? (
          <SkeletonRows />
        ) : rows.length === 0 ? (
          <p className="p-8 text-center text-muted">{t("platformActivity.empty")}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="stack-sm w-full sm:min-w-[720px] text-sm">
              <thead className="bg-paper text-xs text-muted">
                <tr>
                  <th className="px-4 py-3 text-start font-medium">{t("platformActivity.colWhen")}</th>
                  <th className="px-4 py-3 text-start font-medium">{t("platformActivity.colWhat")}</th>
                  <th className="px-4 py-3 text-start font-medium">{t("platformActivity.colKind")}</th>
                  <th className="px-4 py-3 text-start font-medium">{t("platformActivity.colWho")}</th>
                  <th className="px-4 py-3 text-start font-medium">{t("platformActivity.colIp")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {rows.map((row) => (
                  <tr key={row.id} className="align-top">
                    <td className="whitespace-nowrap px-4 py-3 text-muted">{fmt(row.created_at)}</td>
                    <td className="px-4 py-3">
                      <div>{describeActivity(row, t, roleLabel)}</div>
                      {row.entity_type && <div className="mt-0.5 text-xs text-muted">{row.entity_type}{row.entity_id ? ` #${row.entity_id}` : ""}</div>}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3"><Badge>{activityKind(row, t)}</Badge></td>
                    <td className="px-4 py-3">
                      {row.user ? (
                        <>
                          <div className="font-medium">{row.user.full_name || row.user.email}{row.user.id === user?.id && <span className="ms-1 text-xs text-accent">({t("platformTeam.you")})</span>}</div>
                          <div className="text-xs text-muted">{roleLabel(row.user.role_name)}</div>
                        </>
                      ) : (
                        <span className="text-muted">{t("platformActivity.system")}</span>
                      )}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-xs text-muted">{row.ip_address || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {next && (
          <div className="border-t border-line p-3 text-center">
            <Button variant="outline" disabled={loading} onClick={loadMore}>{t("platformActivity.loadMore")}</Button>
          </div>
        )}
      </Card>
    </div>
  );
}
