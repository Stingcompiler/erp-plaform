"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Building2, ChevronDown, ChevronUp, Lock, Search } from "lucide-react";

import { useAuth } from "../../providers/AuthProvider";
import { useI18n } from "../../providers/I18nProvider";
import { platformCompanies as api } from "@/lib/api";
import { Badge, Card, Input, PageHeader } from "@/components/ui/kit";
import PhoneLink from "@/components/ui/PhoneLink";
import UsageMeter, { USAGE_KEYS, usageTone } from "@/components/subscription/UsageMeter";
import DeviceList from "@/components/subscription/DeviceList";
import { useConfirm } from "@/components/ui/ConfirmDialog";

const STATUS_TONE = { active: "ok", trialing: "accent", grace: "warn", read_only: "warn", suspended: "danger", cancelled: "muted", legacy: "muted" };

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
                    <div className="flex items-center gap-2 font-medium"><Building2 size={15} className="text-muted" />{r.name}{r.is_demo && <Badge tone="warn">{t("platformCompanies.demoBadge")}</Badge>}</div>
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
    </div>
  );
}
