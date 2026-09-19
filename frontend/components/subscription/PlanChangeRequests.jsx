"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowUpDown } from "lucide-react";

import { Badge, Button, Card, Input } from "@/components/ui/kit";
import { platformPlanChanges as api } from "@/lib/api";
import { useI18n } from "../../app/providers/I18nProvider";

const KIND_TONE = { upgrade: "ok", downgrade: "warn", addon: "ok", addon_remove: "warn" };

// Pending plan changes for the platform team: who asked, from what to what,
// what an upgrade would bill for the rest of the period, approve or reject.
export default function PlanChangeRequests({ canManage, onChanged }) {
  const { t, language } = useI18n();
  const [rows, setRows] = useState([]);
  const [notes, setNotes] = useState({});
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try { const res = await api.list("pending"); setRows(res.data.results || res.data); }
    catch { /* the badge still says how many wait */ }
  }, []);
  useEffect(() => { load(); }, [load]);

  const decide = async (row, fn) => {
    setBusy(row.id); setError("");
    try { await fn(row.id, notes[row.id] || ""); await load(); onChanged?.(); }
    catch (err) { setError(err?.response?.data?.detail || t("planChange.decideError")); }
    finally { setBusy(null); }
  };
  const fmt = (v) => v ? new Date(v).toLocaleDateString(language === "ar" ? "ar" : "en") : "—";
  const money = (v, c) => `${Number(v || 0).toLocaleString("en", { maximumFractionDigits: 2 })} ${c}`;

  if (!rows.length) return null;
  return (
    <Card className="mb-6 p-5">
      <h2 className="flex items-center gap-2 font-display text-xl font-semibold"><ArrowUpDown size={18} className="text-accent" />{t("planChange.pendingTitle", { n: rows.length })}</h2>
      {error && <p role="alert" className="mt-2 rounded-control bg-danger/10 p-2 text-sm text-danger">{error}</p>}
      <ul className="mt-3 divide-y divide-line">
        {rows.map((r) => (
          <li key={r.id} className="grid gap-3 py-3 lg:grid-cols-[1fr_auto]">
            <div>
              <div className="flex flex-wrap items-center gap-2 font-medium">
                {r.company_name}
                <Badge tone={KIND_TONE[r.kind]}>{t(`planChange.kind.${r.kind}`)}</Badge>
                <span className="text-muted">{r.kind.startsWith("addon")
                  ? `${r.from_plan}: ${Object.entries(r.extra_delta || {}).map(([k, v]) => `${v > 0 ? "+" : ""}${v} ${t(`usage.${k}`)}`).join("، ")}`
                  : <>{r.from_plan} → {r.to_plan}</>}</span>
              </div>
              <div className="mt-0.5 text-xs text-muted">
                {t("planChange.requestedBy", { name: r.requested_by_name, date: fmt(r.created_at) })}
                {!r.kind.startsWith("addon") && <>{" · "}{money(r.from_price, r.currency)} → {money(r.to_price, r.currency)} / {t(`platformPlans.${r.to_cycle}`)}</>}
                {r.note && <> · «{r.note}»</>}
              </div>
              <div className="mt-0.5 text-xs text-muted">{r.kind === "upgrade" || r.kind === "addon" ? t("planChange.upgradeEffect") : t("planChange.downgradeEffect")}</div>
            </div>
            {canManage && (
              <div className="flex flex-wrap items-center gap-2">
                <Input className="w-56" placeholder={t("planChange.decisionNote")} value={notes[r.id] || ""} onChange={(e) => setNotes({ ...notes, [r.id]: e.target.value })} />
                <Button disabled={busy === r.id} onClick={() => decide(r, api.approve)}>{t("planChange.approve")}</Button>
                <Button variant="outline" disabled={busy === r.id} onClick={() => decide(r, api.reject)}>{t("planChange.reject")}</Button>
              </div>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}
