"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Lock, Plus } from "lucide-react";

import { finance } from "@/lib/api";
import { useAuth } from "../../providers/AuthProvider";
import { useI18n } from "../../providers/I18nProvider";
import { useToast } from "@/components/ui/Toast";
import { Badge, Button, Card, Field, Input, PageHeader, Select } from "@/components/ui/kit";
import Drawer from "@/components/ui/Drawer";

function StatTile({ label, value, tone = "ink", hint }) {
  const toneClass = tone === "ok" ? "text-ok" : tone === "danger" ? "text-danger" : "text-ink";
  return (
    <Card className="p-4">
      <div className="text-sm text-muted">{label}</div>
      <div className={`tabular mt-1 text-2xl font-semibold ${toneClass}`}>{value}</div>
      {hint && <div className="mt-1 text-xs text-muted">{hint}</div>}
    </Card>
  );
}

function ExpenseDrawer({ open, writable, onClose, onSaved }) {
  const { t } = useI18n();
  const toast = useToast();
  const today = new Date().toISOString().slice(0, 10);
  const EMPTY = { category: "", description: "", amount: "", method: "cash", date: today };
  const [form, setForm] = useState(EMPTY);
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  useEffect(() => {
    if (open) setForm({ ...EMPTY, date: today });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  async function save() {
    setSaving(true);
    try {
      await finance.createExpense(form);
      toast.success(t("common.save"));
      onSaved?.();
      onClose();
    } catch {
      toast.error(t("finance.saveError"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={t("finance.newExpense")}
      footer={
        writable && (
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={onClose}>{t("common.cancel")}</Button>
            <Button onClick={save} disabled={saving || !form.category || !form.amount || !form.date}>
              {saving ? t("common.saving") : t("finance.recordExpense")}
            </Button>
          </div>
        )
      }
    >
      <div className="space-y-4">
        <Field label={t("finance.category")}>
          <Input value={form.category} onChange={(e) => set("category", e.target.value)} />
        </Field>
        <Field label={t("finance.description")}>
          <Input value={form.description} onChange={(e) => set("description", e.target.value)} />
        </Field>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label={t("finance.amount")}>
            <Input type="number" value={form.amount} onChange={(e) => set("amount", e.target.value)} />
          </Field>
          <Field label={t("finance.date")}>
            <Input type="date" value={form.date} onChange={(e) => set("date", e.target.value)} />
          </Field>
        </div>
        <Field label={t("finance.method")}>
          <Select value={form.method} onChange={(e) => set("method", e.target.value)}>
            <option value="cash">{t("finance.cash")}</option>
            <option value="bank_transfer">{t("finance.bankTransfer")}</option>
          </Select>
        </Field>
      </div>
    </Drawer>
  );
}

export default function FinancePage() {
  const { canRead, canWrite } = useAuth();
  const { t, language } = useI18n();
  const writable = canWrite("finance");
  const [summary, setSummary] = useState(null);
  const [expenses, setExpenses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [page, setPage] = useState(1);
  const [count, setCount] = useState(0);
  const [next, setNext] = useState(false);
  const [filters, setFilters] = useState({ start: "", end: "", search: "", ordering: "-date", method: "standard" });
  const generation = useRef(0);
  const invalidDates = filters.start && filters.end && filters.start > filters.end;
  const money = (v) => v == null ? "—" : Number(v).toLocaleString(language === "ar" ? "ar" : "en", {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  });
  const load = useCallback(async () => {
    const id = ++generation.current;
    setLoading(true); setError(false); setSummary(null);
    try {
      const [totals, rows] = await Promise.all([
        finance.summary({ start: filters.start, end: filters.end, method: filters.method }),
        finance.expenses({ ...filters, page }),
      ]);
      if (id !== generation.current) return;
      setSummary(totals.data); setExpenses(rows.data.results);
      setCount(rows.data.count); setNext(Boolean(rows.data.next));
    } catch { if (id === generation.current) { setError(true); setExpenses([]); } }
    finally { if (id === generation.current) setLoading(false); }
  }, [filters, page]);
  useEffect(() => {
    if (!canRead("finance") || invalidDates) return;
    const timer = setTimeout(load, 250);
    return () => { clearTimeout(timer); generation.current += 1; };
  }, [canRead, load, invalidDates]);
  const change = (key, value) => { setPage(1); setSummary(null); setLoading(true); setFilters((f) => ({ ...f, [key]: value })); };
  if (!canRead("finance")) return <Card className="p-8 text-center"><Lock className="mx-auto" />{t("finance.noAccess")}</Card>;
  return <div>
    <PageHeader title={t("finance.title")} subtitle={t("finance.subtitle")}
      actions={writable && <Button onClick={() => setDrawerOpen(true)}><Plus size={16} />{t("finance.newExpense")}</Button>} />
    <Card className="mb-5 flex flex-wrap items-end gap-3 p-4">
      {["start", "end"].map((key) => <Field key={key} label={t(`improvements.${key}`)}><Input type="date" value={filters[key]} onChange={(e) => change(key,e.target.value)} /></Field>)}
      <Field label={t("reports.costingMethod")}><Select value={filters.method} onChange={(e) => change("method",e.target.value)}>
        <option value="standard">{t("reports.standard")}</option><option value="average">{t("reports.weightedAverage")}</option><option value="fifo">{t("reports.fifo")}</option>
      </Select></Field>
      <Button variant="outline" onClick={() => { setPage(1); setFilters((f) => ({ ...f,start:"",end:"" })); }}>{t("improvements.allTime")}</Button>
    </Card>
    {invalidDates && <p role="alert" className="mb-4 text-danger">{t("improvements.invalidDates")}</p>}
    {error && <Card className="mb-4 p-4"><p role="alert" className="mb-3 text-danger">{t("improvements.loadError")}</p><Button onClick={load}>{t("improvements.retry")}</Button></Card>}
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-busy={loading}>
      <StatTile label={t("finance.revenue")} value={money(summary?.revenue)} hint={t("improvements.revenueHint")} />
      <StatTile label={t("improvements.cogs")} value={money(summary?.cogs)} />
      <StatTile label={t("finance.expenses")} value={money(summary?.expenses)} />
      <StatTile label={t("improvements.netProfit")} value={money(summary?.net)} tone={Number(summary?.net) < 0 ? "danger" : "ok"} />
    </div>
    <p className="mt-3 text-xs text-muted">{t("improvements.accountingNote")}</p>
    <h2 className="mb-3 mt-6 font-display text-lg font-semibold">{t("finance.expensesTab")}</h2>
    <div className="mb-3 flex flex-wrap gap-3">
      <Field label={t("improvements.searchExpenses")}><Input type="search" value={filters.search} onChange={(e) => change("search",e.target.value)} /></Field>
      <Field label={t("improvements.sort")}><Select value={filters.ordering} onChange={(e) => change("ordering",e.target.value)}>
        <option value="-date">{t("improvements.newest")}</option><option value="date">{t("improvements.oldest")}</option><option value="-amount">{t("improvements.highest")}</option>
      </Select></Field>
    </div>
    {loading && !invalidDates && <p role="status" className="py-6 text-muted">{t("common.loading")}</p>}
    {!loading && !error && !invalidDates && <Card>
      {expenses.length === 0 ? <p className="p-8 text-center text-muted">{t("finance.noExpenses")}</p> :
      <div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr className="border-b border-line text-muted">
        {["category","description","method","date","amount"].map((key) => <th key={key} scope="col" className="px-4 py-3 text-start">{t(`finance.${key}`)}</th>)}
      </tr></thead><tbody>{expenses.map((e) => <tr key={e.id} className="border-b border-line last:border-0">
        <td className="px-4 py-3">{e.category}</td><td className="px-4 py-3">{e.description || "—"}</td>
        <td className="px-4 py-3"><Badge>{t(e.method === "cash" ? "finance.cash" : "finance.bankTransfer")}</Badge></td>
        <td className="tabular whitespace-nowrap px-4 py-3">{e.date}</td><td className="tabular px-4 py-3">{money(e.amount)}</td>
      </tr>)}</tbody></table></div>}
      <div className="flex items-center justify-between gap-3 border-t border-line p-3">
        <Button variant="outline" disabled={page <= 1} onClick={() => setPage((p) => p-1)}>{t("improvements.previous")}</Button>
        <span className="text-sm text-muted">{t("improvements.page", {page,pages:Math.max(1,Math.ceil(count/50))})}</span>
        <Button variant="outline" disabled={!next} onClick={() => setPage((p) => p+1)}>{t("improvements.next")}</Button>
      </div>
    </Card>}
    <ExpenseDrawer open={drawerOpen} writable={writable} onClose={() => setDrawerOpen(false)} onSaved={load} />
  </div>;
}
