"use client";
import { useCallback, useEffect, useState } from "react";
import { hr } from "@/lib/api";
import { useI18n } from "../../app/providers/I18nProvider";
import { Badge, Button, Card, Field, Input, Select } from "@/components/ui/kit";

const types = { annual: "hr.typeAnnual", casual: "hr.typeCasual", sick: "hr.typeSick", unpaid: "hr.typeUnpaid", other: "hr.typeOther" };
const empty = { leave_type: "annual", annual_days: "", minimum_service_months: "0", carryover_limit: "0", prorate_first_year: true, is_active: true };
export default function LeavePolicies({ writable }) {
  const { t } = useI18n();
  const [rows, setRows] = useState([]);
  const [form, setForm] = useState(null);
  const [year, setYear] = useState(new Date().getFullYear());
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const load = useCallback(
    () => hr.leaveAccrualPolicies().then(({ data }) => setRows(data.results || data)).catch(() => setError(t("common.loadError"))),
    [t]
  );
  useEffect(() => { load(); }, [load]);
  const set = (key, value) => setForm((current) => ({ ...current, [key]: value }));
  async function save() {
    setSaving(true); setError("");
    const body = { ...form, minimum_service_months: Number(form.minimum_service_months), annual_days: form.annual_days, carryover_limit: form.carryover_limit };
    try {
      if (form.id) await hr.updateLeaveAccrualPolicy(form.id, body);
      else await hr.createLeaveAccrualPolicy(body);
      setForm(null); load();
    } catch { setError(t("hr.policySaveError")); }
    finally { setSaving(false); }
  }
  async function generate() {
    setSaving(true); setError(""); setMessage("");
    try {
      const { data } = await hr.generateLeaveAllowances(year);
      setMessage(t("hr.allowancesGenerated", data));
    } catch { setError(t("hr.allowancesGenerateError")); }
    finally { setSaving(false); }
  }
  return <div className="mt-4 space-y-4">
    <Card className="p-4 text-sm text-muted">{t("hr.policyExplanation")}</Card>
    {writable && <div className="flex flex-wrap items-end gap-3"><Button onClick={() => setForm(empty)}>{t("hr.newLeavePolicy")}</Button><Field label={t("hr.balanceYear")}><Input type="number" min="1900" max="9998" value={year} onChange={(e) => setYear(e.target.value)} /></Field><Button variant="outline" disabled={saving || rows.filter((row) => row.is_active).length === 0} onClick={generate}>{t("hr.generateBalances")}</Button></div>}
    {message && <p className="text-ok">{message}</p>}{error && <p role="alert" className="text-danger">{error}</p>}
    {form && <Card className="space-y-4 p-4"><div className="grid gap-4 sm:grid-cols-2"><Field label={t("hr.leaveRequests")}><Select disabled={Boolean(form.id)} value={form.leave_type} onChange={(e) => set("leave_type", e.target.value)}>{Object.entries(types).map(([value, key]) => <option key={value} value={value}>{t(key)}</option>)}</Select></Field><Field label={t("hr.entitledDays")}><Input type="number" min="0" step="0.01" value={form.annual_days} onChange={(e) => set("annual_days", e.target.value)} /></Field><Field label={t("hr.minimumServiceMonths")}><Input type="number" min="0" max="1200" value={form.minimum_service_months} onChange={(e) => set("minimum_service_months", e.target.value)} /></Field><Field label={t("hr.carryoverLimit")}><Input type="number" min="0" step="0.01" value={form.carryover_limit} onChange={(e) => set("carryover_limit", e.target.value)} /></Field></div><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.prorate_first_year} onChange={(e) => set("prorate_first_year", e.target.checked)} />{t("hr.prorateFirstYear")}</label><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.is_active} onChange={(e) => set("is_active", e.target.checked)} />{t("common.active")}</label><div className="flex gap-2"><Button disabled={saving || form.annual_days === ""} onClick={save}>{t(saving ? "common.saving" : "common.save")}</Button><Button variant="outline" disabled={saving} onClick={() => setForm(null)}>{t("common.cancel")}</Button></div></Card>}
    {rows.length === 0 && <Card className="p-6 text-muted">{t("hr.noLeavePolicies")}</Card>}
    {rows.map((row) => <Card key={row.id} className="flex flex-wrap items-center justify-between gap-3 p-4"><div><strong>{t(types[row.leave_type])}</strong><p className="mt-1 text-sm text-muted">{t("hr.policySummary", { days: row.annual_days, service: row.minimum_service_months, carry: row.carryover_limit })}</p></div><div className="flex items-center gap-2"><Badge tone={row.is_active ? "ok" : "muted"}>{row.is_active ? t("common.active") : t("common.inactive")}</Badge>{writable && <Button variant="outline" onClick={() => setForm(row)}>{t("common.edit")}</Button>}</div></Card>)}
  </div>;
}
