"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowUpDown } from "lucide-react";

import { Badge, Button, Card, Input } from "@/components/ui/kit";
import { subscription as api } from "@/lib/api";
import { useI18n } from "../../app/providers/I18nProvider";

const STATUS_TONE = { pending: "warn", approved: "accent", applied: "ok", rejected: "danger", cancelled: "muted" };

// The owner's side: other plans in the same currency, what moving costs for
// the rest of this period, and the one request that may be open.
export default function PlanChangePanel({ onChanged }) {
  const { t, language } = useI18n();
  const [data, setData] = useState(null);
  const [note, setNote] = useState("");
  const [units, setUnits] = useState({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try { const res = await api.planChanges(); setData(res.data); } catch { /* not on SaaS */ }
  }, []);
  useEffect(() => { load(); }, [load]);

  const money = (v, c) => `${Number(v || 0).toLocaleString("en", { maximumFractionDigits: 2 })} ${c}`;
  const fmt = (v) => v ? new Date(v).toLocaleDateString(language === "ar" ? "ar" : "en") : "—";

  const ask = async (option) => {
    if (!window.confirm(t(option.kind === "upgrade" ? "planChange.confirmUpgrade" : "planChange.confirmDowngrade", { plan: option.plan, amount: money(option.due_now, option.currency) }))) return;
    setBusy(true); setError("");
    try { await api.requestPlanChange(option.version, note); setNote(""); await load(); onChanged?.(); }
    catch (err) {
      const d = err?.response?.data;
      setError(d?.code === "usage_exceeds_target"
        ? t("planChange.overUsage", { what: Object.entries(d.over).map(([k, v]) => `${t(`usage.${k}`)} ${v.used}/${v.limit}`).join("، ") })
        : (d?.detail || d?.to_version || t("planChange.requestError")));
    } finally { setBusy(false); }
  };
  const askAddon = async (addon, delta) => {
    const total = Number(addon.unit_due_now) * delta;
    if (!window.confirm(t(delta > 0 ? "planChange.confirmAddon" : "planChange.confirmAddonRemove", { n: Math.abs(delta), what: t(`usage.${addon.resource}`), amount: money(total, addon.currency) }))) return;
    setBusy(true); setError("");
    try { await api.requestAddon({ [addon.resource]: delta }, note); setNote(""); setUnits({}); await load(); onChanged?.(); }
    catch (err) {
      const d = err?.response?.data;
      setError(d?.code === "usage_exceeds_target"
        ? t("planChange.overUsage", { what: Object.entries(d.over).map(([k, v]) => `${t(`usage.${k}`)} ${v.used}/${v.limit}`).join("، ") })
        : (d?.detail || d?.extra_delta || t("planChange.requestError")));
    } finally { setBusy(false); }
  };
  const cancel = async () => {
    setBusy(true); setError("");
    try { await api.cancelPlanChange(data.current.id); await load(); onChanged?.(); }
    catch (err) { setError(err?.response?.data?.detail || t("planChange.requestError")); }
    finally { setBusy(false); }
  };

  if (!data) return null;
  const current = data.current;
  return (
    <Card className="mt-5 p-5">
      <h2 className="flex items-center gap-2 font-display font-semibold"><ArrowUpDown size={18} className="text-accent" />{t("planChange.title")}</h2>
      <p className="mt-1 text-sm text-muted">{t("planChange.hint")}</p>
      {error && <p role="alert" className="mt-3 rounded-control bg-danger/10 p-3 text-sm text-danger">{error}</p>}

      {current ? (
        <div className="mt-4 rounded-control border border-line bg-paper p-4">
          <div className="flex flex-wrap items-center gap-2 font-medium">
            <Badge tone={STATUS_TONE[current.status]}>{t(`planChange.status.${current.status}`)}</Badge>
            {current.kind.startsWith("addon")
              ? Object.entries(current.extra_delta || {}).map(([k, v]) => `${v > 0 ? "+" : ""}${v} ${t(`usage.${k}`)}`).join("، ")
              : <>{current.from_plan} → {current.to_plan}</>}
            <Badge tone={current.kind === "upgrade" || current.kind === "addon" ? "ok" : "warn"}>{t(`planChange.kind.${current.kind}`)}</Badge>
          </div>
          <p className="mt-2 text-sm text-muted">
            {current.status === "pending" && t("planChange.waitingDecision")}
            {current.status === "approved" && current.invoice_number && t("planChange.payToSwitch", { number: current.invoice_number, amount: money(current.invoice_amount, current.currency) })}
            {current.status === "approved" && !current.invoice_number && t("planChange.switchesOn", { date: fmt(current.apply_at) })}
          </p>
          <Button variant="outline" className="mt-3" disabled={busy} onClick={cancel}>{t("planChange.withdraw")}</Button>
        </div>
      ) : (
        <>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {data.options.map((o) => {
              const blocked = Object.keys(o.blocked_by || {}).length > 0;
              return (
                <div key={o.version} className={`rounded-control border p-4 ${blocked ? "border-line opacity-70" : "border-line"}`}>
                  <div className="flex items-center justify-between gap-2">
                    <div className="font-display font-semibold">{o.plan}</div>
                    <Badge tone={o.kind === "upgrade" ? "ok" : "warn"}>{t(`planChange.kind.${o.kind}`)}</Badge>
                  </div>
                  <div className="mt-1 text-sm">{money(o.price, o.currency)} / {t(`platformPlans.${o.billing_cycle}`)}</div>
                  <div className="mt-1 text-xs text-muted">
                    {Object.entries(o.limits || {}).map(([k, v]) => `${t(`usage.${k}`)}: ${v}`).join(" · ") || t("platformPlans.noLimits")}
                  </div>
                  <div className="mt-2 text-sm">
                    {o.kind === "upgrade"
                      ? t("planChange.dueNow", { amount: money(o.due_now, o.currency) })
                      : blocked
                        ? <span className="text-danger">{t("planChange.overUsage", { what: Object.entries(o.blocked_by).map(([k, v]) => `${t(`usage.${k}`)} ${v.used}/${v.limit}`).join("، ") })}</span>
                        : t("planChange.atPeriodEnd")}
                  </div>
                  <Button className="mt-3" disabled={busy || blocked} onClick={() => ask(o)}>{t(o.kind === "upgrade" ? "planChange.askUpgrade" : "planChange.askDowngrade")}</Button>
                </div>
              );
            })}
            {!data.options.length && <p className="text-sm text-muted md:col-span-2">{t("planChange.noOptions")}</p>}
          </div>
          {data.addons?.length > 0 && (
            <div className="mt-5">
              <h3 className="font-display font-semibold">{t("planChange.addonsTitle")}</h3>
              <p className="mt-1 text-sm text-muted">{t("planChange.addonsHint")}</p>
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                {data.addons.map((ad) => {
                  const n = Number(units[ad.resource] ?? 1);
                  return (
                    <div key={ad.resource} className="rounded-control border border-line p-4">
                      <div className="flex items-center justify-between gap-2">
                        <div className="font-display font-semibold">{t(`usage.${ad.resource}`)}</div>
                        <span className="text-sm text-muted">{t("planChange.addonOwned", { plan: ad.plan_limit, extra: ad.owned })}</span>
                      </div>
                      <div className="mt-1 text-sm">{t("planChange.unitPrice", { amount: money(ad.unit_price, ad.currency), cycle: t(`platformPlans.${ad.billing_cycle}`) })}</div>
                      <div className="mt-3 flex flex-wrap items-center gap-2">
                        <Input type="number" min="1" className="w-24" value={n} onChange={(e) => setUnits({ ...units, [ad.resource]: e.target.value })} />
                        <Button disabled={busy || n < 1} onClick={() => askAddon(ad, n)}>{t("planChange.addUnits", { n })}</Button>
                        {ad.owned > 0 && <Button variant="outline" disabled={busy || n < 1 || n > ad.owned} onClick={() => askAddon(ad, -n)}>{t("planChange.removeUnits", { n })}</Button>}
                      </div>
                      <div className="mt-2 text-xs text-muted">{t("planChange.addonDueNow", { amount: money(Number(ad.unit_due_now) * n, ad.currency) })}</div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
          {(data.options.length > 0 || data.addons?.length > 0) && <Input className="mt-3" placeholder={t("planChange.notePlaceholder")} value={note} onChange={(e) => setNote(e.target.value)} />}
        </>
      )}

      {data.history?.length > 0 && (
        <details className="mt-4 text-sm">
          <summary className="cursor-pointer text-muted">{t("planChange.history")}</summary>
          <ul className="mt-2 divide-y divide-line">
            {data.history.map((h) => (
              <li key={h.id} className="flex flex-wrap items-center gap-2 py-2">
                <span className="text-muted">{fmt(h.created_at)}</span>
                <span>{h.kind.startsWith("addon") ? Object.entries(h.extra_delta || {}).map(([k, v]) => `${v > 0 ? "+" : ""}${v} ${t(`usage.${k}`)}`).join("، ") : `${h.from_plan} → ${h.to_plan}`}</span>
                <Badge tone="muted">{t(`planChange.kind.${h.kind}`)}</Badge>
                <Badge tone={STATUS_TONE[h.status]}>{t(`planChange.status.${h.status}`)}</Badge>
                {h.decision_note && <span className="text-muted">«{h.decision_note}»</span>}
              </li>
            ))}
          </ul>
        </details>
      )}
    </Card>
  );
}
