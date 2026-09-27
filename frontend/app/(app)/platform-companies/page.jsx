"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Building2, ChevronDown, ChevronUp, Download, Lock, PauseCircle, PlayCircle, RotateCcw, Search, Trash2 } from "lucide-react";

import { useAuth } from "../../providers/AuthProvider";
import { useI18n } from "../../providers/I18nProvider";
import { platformCompanies as api } from "@/lib/api";
import { Badge, Button, Card, Input, PageHeader } from "@/components/ui/kit";
import { errorText } from "@/lib/errors";
import PhoneLink from "@/components/ui/PhoneLink";
import UsageMeter, { USAGE_KEYS, usageTone } from "@/components/subscription/UsageMeter";
import DeviceList from "@/components/subscription/DeviceList";
import { useConfirm } from "@/components/ui/ConfirmDialog";

const STATUS_TONE = { active: "ok", trialing: "accent", grace: "warn", read_only: "warn", suspended: "danger", cancelled: "muted", legacy: "muted" };

// What the typed confirmation must match: the name or the slug, ignoring
// case and extra spaces — the server checks the same (company_deletion).
const fold = (value) => String(value || "").trim().split(/\s+/).join(" ").toLowerCase();
const matchesCompany = (typed, row) => {
  const value = fold(typed);
  return Boolean(value) && (value === fold(row.name) || value === fold(row.slug));
};

function Cell({ cell }) {
  const tone = usageTone(cell);
  const cls = { danger: "text-danger font-semibold", warn: "text-warn font-semibold", ok: "", muted: "text-muted" }[tone];
  return <span dir="ltr" className={`tabular ${cls}`}>{cell.used}<span className="text-muted">/{cell.limit ?? "∞"}</span></span>;
}

export default function PlatformCompaniesPage() {
  const { can } = useAuth();
  const { t, language } = useI18n();
  const confirm = useConfirm();
  const canView = can("platform.subscriptions.view");
  const canManage = can("platform.subscriptions.manage");
  // Owner controls (core/platform_roles.py): suspending is a collections
  // decision; deleting a company is the platform owner's by default.
  const canSuspend = can("platform.companies.suspend");
  const canDelete = can("platform.companies.delete");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(null);
  const [devices, setDevices] = useState({});
  const [busy, setBusy] = useState(null);

  const load = useCallback(async () => {
    try { const res = await api.list(); setData(res.data); setError(""); }
    catch { setError(t("platformCompanies.loadError")); }
  }, [t]);
  useEffect(() => { if (canView) load(); }, [canView, load]);

  const loadDevices = useCallback(async (id) => {
    try { const res = await api.devices(id); setDevices((cur) => ({ ...cur, [id]: res.data.devices })); } catch { /* row stays collapsed */ }
  }, []);
  const toggle = (id) => { const next = open === id ? null : id; setOpen(next); if (next && !devices[next]) loadDevices(next); };
  const deviceAction = async (companyId, fn, deviceId) => {
    setBusy(deviceId); setError("");
    try { await fn(); await loadDevices(companyId); await load(); }
    catch (err) { const d = err?.response?.data; setError(d?.code === "plan_limit_reached" ? t("devices.noRoom", { limit: d.limit }) : (d?.detail || t("platformCompanies.loadError"))); }
    finally { setBusy(null); }
  };

  // The demo mark labels a sample tenant's public page and showcase card.
  const setDemo = async (companyId, isDemo) => {
    setBusy(`demo-${companyId}`); setError("");
    try { await api.setDemo(companyId, isDemo); await load(); }
    catch { setError(t("platformCompanies.loadError")); }
    finally { setBusy(null); }
  };

  // One place for every owner control: busy flag, the call, reload, and an
  // Arabic/English sentence when the server refuses.
  const control = async (key, fn) => {
    setBusy(key); setError("");
    try { await fn(); await load(); }
    catch (err) { setError(errorText(err, t, "platformCompanies.actionError")); }
    finally { setBusy(null); }
  };
  const suspend = async (r) => {
    const reason = await confirm(t("platformCompanies.suspendPrompt", { name: r.name }), {
      tone: "danger", confirmLabel: t("platformCompanies.suspend"),
      input: { label: t("platformCompanies.suspendReason"), required: true },
    });
    if (reason === false) return;
    control(`suspend-${r.id}`, () => api.suspend(r.id, reason));
  };
  const lift = async (r) => {
    if (!(await confirm(t("platformCompanies.liftConfirm", { name: r.name })))) return;
    control(`lift-${r.id}`, () => api.liftSuspension(r.id));
  };
  // Typed confirmation, checked here for a clear message and again on the
  // server, which refuses a mismatch whatever the page sends.
  const typedConfirm = async (r, message, confirmLabel) => {
    const warning = r.pending_payments ? `\n\n${t("platformCompanies.pendingWarning", { n: r.pending_payments })}` : "";
    const typed = await confirm(message + warning, {
      tone: "danger", confirmLabel,
      input: { label: t("platformCompanies.confirmLabel"), required: true },
    });
    if (typed === false) return null;
    if (!matchesCompany(typed, r)) { setError(t("platformCompanies.confirmMismatch")); return null; }
    return typed;
  };
  const remove = async (r) => {
    const purgeOn = fmtDate(new Date(Date.now() + 30 * 24 * 3600 * 1000));
    const typed = await typedConfirm(r, t("platformCompanies.deletePrompt", { name: r.name, slug: r.slug, date: purgeOn }), t("platformCompanies.delete"));
    if (typed) control(`delete-${r.id}`, () => api.remove(r.id, typed));
  };
  const restore = async (r) => {
    if (!(await confirm(t("platformCompanies.restoreConfirm", { name: r.name })))) return;
    control(`restore-${r.id}`, () => api.restore(r.id));
  };
  const purge = async (r) => {
    const typed = await typedConfirm(r, t("platformCompanies.purgePrompt", { name: r.name, slug: r.slug }), t("platformCompanies.purgeNow"));
    if (typed) control(`purge-${r.id}`, () => api.purge(r.id, typed));
  };

  const rows = useMemo(() => {
    const list = data?.companies || [];
    const q = query.trim().toLowerCase();
    const filtered = q ? list.filter((r) => [r.name, r.slug, r.owner?.email, r.owner?.name, r.owner?.phone].some((v) => (v || "").toLowerCase().includes(q))) : list;
    // Companies over their plan first: that is what this page is for.
    return [...filtered].sort((a, b) => (b.over_limit.length - a.over_limit.length) || a.name.localeCompare(b.name));
  }, [data, query]);

  const fmt = (value) => value ? new Date(value).toLocaleString(language === "ar" ? "ar" : "en", { dateStyle: "medium", timeStyle: "short" }) : "—";
  const fmtDate = (value) => value ? new Date(value).toLocaleDateString(language === "ar" ? "ar" : "en") : "—";

  if (!canView) return <Card className="mx-auto mt-16 max-w-md p-8 text-center"><Lock className="mx-auto text-muted" /><p className="mt-3 text-muted">{t("platformCompanies.noAccess")}</p></Card>;

  const overCount = (data?.companies || []).filter((r) => r.over_limit.length).length;
  return (
    <div>
      <PageHeader title={t("platformCompanies.title")} subtitle={t("platformCompanies.subtitle")} />
      {error && <div role="alert" className="mb-4 rounded-control bg-danger/10 p-3 text-sm text-danger">{error}</div>}
      {data && data.policy !== "enforce" && (
        <div role="alert" className="mb-4 rounded-control border border-warn/30 bg-warn/10 p-3 text-sm">
          {t("platformCompanies.policyWarning", { policy: data.policy })}
        </div>
      )}
      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <Card className="p-4"><div className="text-xs text-muted">{t("platformCompanies.total")}</div><div className="mt-1 font-display text-2xl font-semibold tabular">{data?.companies?.length ?? "—"}</div></Card>
        <Card className="p-4"><div className="text-xs text-muted">{t("platformCompanies.overLimit")}</div><div className={`mt-1 font-display text-2xl font-semibold tabular ${overCount ? "text-danger" : ""}`}>{data ? overCount : "—"}</div></Card>
        <Card className="p-4"><div className="text-xs text-muted">{t("platformCompanies.devicesTotal")}</div><div className="mt-1 font-display text-2xl font-semibold tabular">{data ? data.companies.reduce((n, r) => n + (r.usage?.devices?.used || 0), 0) : "—"}</div></Card>
      </div>
      <div className="relative mb-4 max-w-md">
        <Search size={16} className="pointer-events-none absolute start-3 top-1/2 -translate-y-1/2 text-muted" />
        <Input className="ps-9" placeholder={t("platformCompanies.search")} value={query} onChange={(e) => setQuery(e.target.value)} />
      </div>
      <Card className="overflow-x-auto">
        <table className="stack-sm w-full sm:min-w-[880px] text-sm">
          <thead className="bg-paper text-start text-xs uppercase tracking-wide text-muted">
            <tr>
              <th className="px-4 py-3 text-start">{t("platformCompanies.company")}</th>
              <th className="px-4 py-3 text-start">{t("platformCompanies.plan")}</th>
              {USAGE_KEYS.map((key) => <th key={key} className="px-3 py-3 text-center">{t(`usage.${key}`)}</th>)}
              <th className="px-4 py-3 text-start">{t("platformCompanies.owner")}</th>
              <th className="px-4 py-3 text-start">{t("platformCompanies.activity")}</th>
              <th className="w-10" />
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {rows.map((r) => (
              <>
                <tr key={r.id} className={`cursor-pointer hover:bg-paper ${r.over_limit.length ? "bg-danger/5" : ""}`} onClick={() => toggle(r.id)}>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap items-center gap-2 font-medium"><Building2 size={15} className="text-muted" />{r.name}{r.is_demo && <Badge tone="warn">{t("platformCompanies.demoBadge")}</Badge>}
                      {r.suspension && <Badge tone="danger">{t(r.suspension.kind === "unpaid" ? "platformCompanies.suspendedUnpaid" : "platformCompanies.suspendedManual")}</Badge>}
                      {r.deletion && <Badge tone="danger">{t("platformCompanies.scheduledDeletion", { date: fmtDate(r.deletion.purge_after) })}</Badge>}
                    </div>
                    <div className="mt-0.5 text-xs text-muted">{t(`platformCompanies.type.${r.business_type}`)} · {t("platformCompanies.since")} {fmtDate(r.created_at)}{r.over_limit.length > 0 && <> · <span className="text-danger">{t("platformCompanies.overOn", { what: r.over_limit.map((k) => t(`usage.${k}`)).join("، ") })}</span></>}</div>
                  </td>
                  <td className="px-4 py-3">{r.plan ? <><div>{r.plan.name || "—"}</div><Badge tone={STATUS_TONE[r.plan.status] || "muted"}>{t(`platformCompanies.status.${r.plan.status}`)}</Badge></> : <Badge tone="muted">{t("platformCompanies.noPlan")}</Badge>}</td>
                  {USAGE_KEYS.map((key) => <td key={key} className="px-3 py-3 text-center"><Cell cell={r.usage[key]} /></td>)}
                  <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>{r.owner ? <><div>{r.owner.name || r.owner.email}</div><div className="text-xs text-muted"><a className="hover:underline" href={`mailto:${r.owner.email}`}>{r.owner.email}</a>{r.owner.phone && <> · <PhoneLink phone={r.owner.phone} /></>}</div></> : "—"}</td>
                  <td className="px-4 py-3 text-xs text-muted"><div>{t("platformCompanies.lastActive")}: {fmt(r.last_active_at)}</div><div>{t("platformCompanies.invoices30d", { n: r.invoices_30d })}</div></td>
                  <td className="px-2 text-muted">{open === r.id ? <ChevronUp size={16} /> : <ChevronDown size={16} />}</td>
                </tr>
                {open === r.id && (
                  <tr key={`${r.id}-detail`} className="bg-paper/60">
                    <td colSpan={5 + USAGE_KEYS.length} className="px-4 py-4">
                      {(canSuspend || canDelete) && (
                        <div className="mb-4 rounded-control border border-line bg-surface p-3">
                          <h3 className="mb-2 font-display text-sm font-semibold">{t("platformCompanies.ownerControls")}</h3>
                          {r.suspension?.kind === "unpaid" && <p className="mb-2 text-sm text-danger">{t("platformCompanies.suspendedSince", { date: fmtDate(r.suspension.since), reason: r.suspension.reason })}</p>}
                          {r.suspension?.kind === "manual" && <p className="mb-2 text-sm text-muted">{t("platformCompanies.manualSuspendHint", { reason: r.suspension.reason || "—" })}</p>}
                          {r.deletion && <p className="mb-2 text-sm text-danger">{t("platformCompanies.deletionInfo", { date: fmtDate(r.deletion.purge_after), by: r.deletion.requested_by || "—", rows: r.deletion.backup_rows })}</p>}
                          {r.pending_payments > 0 && <p className="mb-2 text-xs text-warn">{t("platformCompanies.pendingWarning", { n: r.pending_payments })}</p>}
                          <div className="flex flex-wrap gap-2">
                            {canSuspend && !r.deletion && !r.suspension && r.plan && (
                              <Button variant="outline" disabled={busy === `suspend-${r.id}`} onClick={() => suspend(r)}><PauseCircle size={15} />{t("platformCompanies.suspend")}</Button>
                            )}
                            {canSuspend && r.suspension?.kind === "unpaid" && (
                              <Button variant="outline" disabled={busy === `lift-${r.id}`} onClick={() => lift(r)}><PlayCircle size={15} />{t("platformCompanies.lift")}</Button>
                            )}
                            {canDelete && !r.deletion && (
                              <Button variant="danger" disabled={busy === `delete-${r.id}`} onClick={() => remove(r)}><Trash2 size={15} />{t("platformCompanies.delete")}</Button>
                            )}
                            {canDelete && r.deletion && (
                              <>
                                <Button variant="outline" disabled={busy === `restore-${r.id}`} onClick={() => restore(r)}><RotateCcw size={15} />{t("platformCompanies.restore")}</Button>
                                <a className="tap inline-flex min-h-10 items-center gap-2 rounded-control border border-line bg-surface px-4 py-2 text-sm font-semibold hover:bg-paper" href={api.backupUrl(r.id)}><Download size={15} />{t("platformCompanies.downloadBackup")}</a>
                                <Button variant="danger" disabled={busy === `purge-${r.id}`} onClick={() => purge(r)}><Trash2 size={15} />{t("platformCompanies.purgeNow")}</Button>
                              </>
                            )}
                          </div>
                        </div>
                      )}
                      <label className={`mb-4 inline-flex items-center gap-2 text-sm ${canManage ? "cursor-pointer" : "opacity-70"}`}>
                        <input
                          type="checkbox" className="accent-accent" checked={!!r.is_demo}
                          disabled={!canManage || busy === `demo-${r.id}`}
                          onChange={(e) => setDemo(r.id, e.target.checked)}
                        />
                        {t("platformCompanies.demoToggle")}
                      </label>
                      <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
                        <div><h3 className="mb-3 font-display font-semibold">{t("subscription.limits")}</h3><UsageMeter usage={r.usage} /></div>
                        <div>
                          <h3 className="mb-3 font-display font-semibold">{t("devices.title")}</h3>
                          <DeviceList
                            devices={devices[r.id]}
                            busyId={busy}
                            onRevoke={canManage ? async (d) => { if ((await confirm(t("devices.confirmRevoke", { name: d.label || d.device_id }), { tone: "danger" }))) deviceAction(r.id, () => api.revokeDevice(r.id, d.id), d.id); } : undefined}
                            onReactivate={canManage ? (d) => deviceAction(r.id, () => api.reactivateDevice(r.id, d.id), d.id) : undefined}
                          />
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </>
            ))}
            {data && !rows.length && <tr><td colSpan={5 + USAGE_KEYS.length} className="px-4 py-10 text-center text-muted">{t("platformCompanies.empty")}</td></tr>}
          </tbody>
        </table>
      </Card>
      {canDelete && data?.purged?.length > 0 && (
        <Card className="mt-6 p-4">
          <h2 className="mb-3 font-display font-semibold">{t("platformCompanies.purgedTitle")}</h2>
          <ul className="divide-y divide-line text-sm">
            {data.purged.map((p) => (
              <li key={p.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <span><span className="font-medium">{p.name}</span> <bdi dir="ltr" className="text-xs text-muted">{p.slug}</bdi> · <span className="text-muted">{t("platformCompanies.purgedOn", { date: fmtDate(p.purged_at) })}</span></span>
                {p.backup_id && <a className="inline-flex items-center gap-1 text-accent hover:underline" href={api.backupUrl(p.id)}><Download size={14} />{t("platformCompanies.downloadBackup")}</a>}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
