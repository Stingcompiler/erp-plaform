"use client";
import { useEffect, useState } from "react";
import { hr } from "@/lib/api";
import { useI18n } from "../../app/providers/I18nProvider";
import { Button, Card, Field, Input, Select } from "@/components/ui/kit";
import { SkeletonLines } from "@/components/ui/Skeleton";

const types = { annual: "hr.typeAnnual", casual: "hr.typeCasual", sick: "hr.typeSick", unpaid: "hr.typeUnpaid", other: "hr.typeOther" };
export default function LeaveBalances({ writable }) {
  const { t } = useI18n();
  const [year, setYear] = useState(new Date().getFullYear());
  const [page, setPage] = useState(1);
  const [data, setData] = useState({ results: [], next: null });
  const [employees, setEmployees] = useState([]);
  const [form, setForm] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let alive = true;
    setLoading(true); setError("");
    hr.leaveAllowances({ year, page }).then(({ data: result }) => { if (alive) setData(result); })
      .catch(() => { if (alive) setError(t("common.loadError")); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [year, page, revision, t]);
  useEffect(() => {
    if (!writable) return;
    let alive = true;
    (async () => {
      const rows = []; let current = 1;
      while (alive) {
        const { data: result } = await hr.employees({ page: current });
        rows.push(...result.results);
        if (!result.next) break;
        current += 1;
      }
      if (alive) setEmployees(rows);
    })().catch(() => { if (alive) setError(t("common.loadError")); });
    return () => { alive = false; };
  }, [writable, t]);
  const set = (key, value) => setForm((old) => ({ ...old, [key]: value }));
  async function save() {
    setSaving(true); setError("");
    const body = { employee: form.employee, year, leave_type: form.leave_type, entitled_days: form.entitled_days, carried_days: form.carried_days, note: form.note };
    try {
      if (form.id) await hr.updateLeaveAllowance(form.id, body);
      else await hr.createLeaveAllowance(body);
      setForm(null); setRevision((value) => value + 1);
    } catch { setError(t("hr.balanceSaveError")); }
    finally { setSaving(false); }
  }
  return <div className="mt-4 space-y-4">
    <Card className="p-4 text-sm text-muted">{t("hr.balanceExplanation")}</Card>
    <div className="flex flex-wrap items-end gap-3">
      <Field label={t("hr.balanceYear")}><Input type="number" min="1900" max="9998" value={year} onChange={(e) => { setYear(e.target.value); setPage(1); setForm(null); }} /></Field>
      {writable && <Button onClick={() => setForm({ employee: "", leave_type: "annual", entitled_days: "", carried_days: "0", note: "" })}>{t("hr.configureBalance")}</Button>}
    </div>
    {error && <p role="alert" className="text-danger">{error}</p>}
    {form && <Card className="space-y-4 p-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label={t("hr.employees")}><Select value={form.employee} disabled={Boolean(form.id)} onChange={(e) => set("employee", e.target.value)}><option value="">—</option>{employees.map((employee) => <option key={employee.id} value={employee.id}>{employee.full_name}</option>)}</Select></Field>
        <Field label={t("hr.leaveRequests")}><Select value={form.leave_type} disabled={Boolean(form.id)} onChange={(e) => set("leave_type", e.target.value)}>{Object.entries(types).map(([value, key]) => <option key={value} value={value}>{t(key)}</option>)}</Select></Field>
        <Field label={t("hr.entitledDays")}><Input type="number" min="0" step="0.01" value={form.entitled_days} onChange={(e) => set("entitled_days", e.target.value)} /></Field>
        <Field label={t("hr.carriedDays")}><Input type="number" min="0" step="0.01" value={form.carried_days} onChange={(e) => set("carried_days", e.target.value)} /></Field>
      </div>
      <Field label={t("hr.balanceReason")}><Input maxLength={1000} value={form.note} onChange={(e) => set("note", e.target.value)} /></Field>
      <div className="flex gap-2"><Button disabled={saving || !form.employee || form.entitled_days === "" || !form.note.trim()} onClick={save}>{t(saving ? "common.saving" : "common.save")}</Button><Button variant="outline" disabled={saving} onClick={() => setForm(null)}>{t("common.cancel")}</Button></div>
    </Card>}
    {loading ? <SkeletonLines /> : !error && <>
      {data.results.length === 0 && <Card className="p-6 text-muted">{t("hr.noBalances")}</Card>}
      {data.results.map((row) => <Card key={row.id} className="space-y-3 p-4">
        <div className="flex items-center justify-between gap-3"><strong>{row.employee_name} · {t(types[row.leave_type])}</strong>{writable && <Button variant="outline" onClick={() => setForm({ ...row, note: "" })}>{t("hr.adjustBalance")}</Button>}</div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">{[["total_days", "hr.totalDays"], ["used_days", "hr.usedDays"], ["pending_days", "hr.pendingDays"], ["remaining_days", "hr.remainingDays"]].map(([key, label]) => <div key={key}><div className="text-sm text-muted">{t(label)}</div><div className="tabular text-xl font-semibold">{row.balance[key]}</div></div>)}</div>
        <p className="text-sm text-muted">{row.note}</p>
      </Card>)}
      <div className="flex items-center gap-3"><Button aria-label={t("hr.previousPage")} variant="outline" disabled={page === 1} onClick={() => setPage(page - 1)}>←</Button><span>{page}</span><Button aria-label={t("hr.nextPage")} variant="outline" disabled={!data.next} onClick={() => setPage(page + 1)}>→</Button></div>
    </>}
  </div>;
}
