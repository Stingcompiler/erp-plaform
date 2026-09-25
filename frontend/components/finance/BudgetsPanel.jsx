"use client";

import { useCallback, useEffect, useState } from "react";
import { BadgeCheck, ChevronDown, ChevronUp, Plus, RotateCcw, Scale, Trash2 } from "lucide-react";

import { finance } from "@/lib/api";
import { useAuth } from "../../app/providers/AuthProvider";
import { useI18n } from "../../app/providers/I18nProvider";
import { useToast } from "@/components/ui/Toast";
import Drawer from "@/components/ui/Drawer";
import { Badge, Button, Card, Field, Input, Select } from "@/components/ui/kit";
import { errorText } from "@/lib/errors";
import { SkeletonLines, SkeletonRows } from "@/components/ui/Skeleton";
import { expenseCategory } from "@/lib/expenseCategories";
import { formatAmount } from "@/lib/money";

const money = (v) =>
  formatAmount(v);
const TONE = { draft: "muted", approved: "ok", archived: "muted" };

function NewBudgetDrawer({ open, onClose, categories, onSaved }) {
  const { t } = useI18n();
  const [name, setName] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [lines, setLines] = useState([{ kind: "expense", category: "", planned_amount: "" }]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) { setName(""); setStart(""); setEnd(""); setLines([{ kind: "expense", category: "", planned_amount: "" }]); setError(""); }
  }, [open]);
  const patch = (i, f) => setLines((ls) => ls.map((l, j) => (j === i ? { ...l, ...f } : l)));

  async function save() {
    setError("");
    const clean = lines.filter((l) => l.category.trim() && Number(l.planned_amount) > 0);
    if (!name.trim() || !start || !end) return setError(t("budgets.headerRequired"));
    if (!clean.length) return setError(t("budgets.linesRequired"));
    setBusy(true);
    try {
      const r = await finance.createBudget({
        name: name.trim(), period_start: start, period_end: end,
        lines: clean.map((l) => ({ kind: l.kind, category: l.category.trim(), planned_amount: l.planned_amount })),
      });
      onSaved?.(r.data); onClose();
    } catch (err) {
      setError(errorText(err, t, "budgets.saveError"));
    } finally { setBusy(false); }
  }

  return (
    <Drawer open={open} onClose={onClose} title={t("budgets.newTitle")} wide
      footer={<div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>{t("common.cancel")}</Button>
        <Button onClick={save} disabled={busy}>{busy ? t("common.saving") : t("budgets.create")}</Button>
      </div>}>
      <div className="space-y-4">
        <Field label={t("budgets.name")}><Input value={name} onChange={(e) => setName(e.target.value)} autoFocus /></Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t("budgets.periodStart")}><Input type="date" value={start} onChange={(e) => setStart(e.target.value)} /></Field>
          <Field label={t("budgets.periodEnd")}><Input type="date" value={end} onChange={(e) => setEnd(e.target.value)} /></Field>
        </div>
        <div>
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-sm font-semibold">{t("budgets.lines")}</h3>
            <Button variant="ghost" onClick={() => setLines((ls) => [...ls, { kind: "expense", category: "", planned_amount: "" }])}><Plus size={14} />{t("budgets.addLine")}</Button>
          </div>
          <datalist id="budget-categories">{categories.map((c) => <option key={c} value={c} />)}</datalist>
          <div className="space-y-2">
            {lines.map((l, i) => (
              <div key={i} className="flex flex-wrap items-center gap-2">
                <div className="w-32"><Select value={l.kind} onChange={(e) => patch(i, { kind: e.target.value })} aria-label={t("budgets.kind")}>
                  <option value="expense">{t("budgets.expense")}</option>
                  <option value="revenue">{t("budgets.revenue")}</option>
                </Select></div>
                <div className="min-w-0 flex-1"><Input list="budget-categories" value={l.category} onChange={(e) => patch(i, { category: e.target.value })} placeholder={t("budgets.category")} aria-label={t("budgets.category")} /></div>
                <div className="w-32"><Input type="number" inputMode="decimal" min="0" step="0.01" value={l.planned_amount} onChange={(e) => patch(i, { planned_amount: e.target.value })} placeholder="0.00" aria-label={t("budgets.planned")} className="text-end" /></div>
                <button onClick={() => setLines((ls) => ls.filter((_, j) => j !== i))} className="text-muted hover:text-danger" aria-label={t("common.remove")}><Trash2 size={15} /></button>
              </div>
            ))}
          </div>
          <p className="mt-2 text-xs text-muted">{t("budgets.categoryHint")}</p>
        </div>
        {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      </div>
    </Drawer>
  );
}

function VarianceTable({ budgetId }) {
  const { t } = useI18n();
  const [data, setData] = useState(null);
  useEffect(() => { finance.budgetVariance(budgetId).then((r) => setData(r.data)).catch(() => setData({ rows: [] })); }, [budgetId]);
  if (!data) return <SkeletonLines />;
  if (!data.rows.length) return <p className="px-4 py-3 text-sm text-muted">{t("budgets.noLines")}</p>;
  return (
    <div className="overflow-x-auto border-t border-line">
      <table className="stack-sm w-full text-sm">
        <thead><tr className="border-b border-line text-xs uppercase tracking-wide text-muted">
          <th className="px-3 py-2 text-start font-medium">{t("budgets.category")}</th>
          <th className="px-3 py-2 text-end font-medium">{t("budgets.planned")}</th>
          <th className="px-3 py-2 text-end font-medium">{t("budgets.actual")}</th>
          <th className="px-3 py-2 text-end font-medium">{t("budgets.variance")}</th>
        </tr></thead>
        <tbody>{data.rows.map((r) => (
          <tr key={`${r.kind}-${r.category}`} className="border-b border-line last:border-0">
            <td className="px-3 py-2"><span className="inline-flex items-center gap-2">{expenseCategory(r.category, t)}<Badge tone="muted">{t(`budgets.${r.kind}`)}</Badge></span></td>
            <td className="tabular px-3 py-2 text-end text-muted">{money(r.planned)}</td>
            <td className="tabular px-3 py-2 text-end">{money(r.actual)}</td>
            <td className={`tabular px-3 py-2 text-end font-medium ${r.favourable ? "text-ok" : "text-danger"}`}>{money(r.variance)}{r.variance_pct != null && <span className="ms-1 text-xs text-muted">({r.variance_pct}%)</span>}</td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

/**
 * Budgets: approve a period's plan per category, then watch actual
 * expenses (and invoiced revenue) against it. The API had draft/approved/
 * archived and a variance report; no screen ever showed them, and the
 * free-text expense category could not match a plan — the shared category
 * list (finance.categories) fixes the second half.
 */
export default function BudgetsPanel({ writable, categories, onChanged }) {
  const { t, language } = useI18n();
  const { can } = useAuth();
  const toast = useToast();
  const approver = can("finance.approve");
  const [rows, setRows] = useState(null);
  const [openId, setOpenId] = useState(null);
  const [drawer, setDrawer] = useState(false);
  const [busy, setBusy] = useState(null);

  const load = useCallback(() => {
    finance.budgets({ page_size: 50 }).then((r) => setRows(r.data.results ?? r.data)).catch(() => setRows([]));
  }, []);
  useEffect(() => { load(); }, [load]);

  const act = async (id, fn, ok) => {
    setBusy(id);
    try { await fn(id); toast.success(ok); load(); }
    catch (err) { toast.error(errorText(err, t, "budgets.actionError")); }
    finally { setBusy(null); }
  };
  const fmt = (d) => new Date(`${d}T00:00:00`).toLocaleDateString(language === "ar" ? "ar" : "en");

  return (
    <Card className="mt-5">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line p-4">
        <h2 className="flex items-center gap-2 font-display text-lg font-semibold"><Scale size={18} className="text-accent" />{t("budgets.title")}</h2>
        {writable && <Button onClick={() => setDrawer(true)}><Plus size={16} />{t("budgets.new")}</Button>}
      </div>
      {rows === null ? <SkeletonRows /> : rows.length === 0 ? (
        <p className="p-8 text-center text-muted">{t("budgets.empty")}</p>
      ) : (
        <div className="divide-y divide-line">
          {rows.map((b) => (
            <div key={b.id}>
              <div className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2"><span className="font-medium">{b.name}</span><Badge tone={TONE[b.status] || "muted"}>{t(`budgets.status.${b.status}`)}</Badge></div>
                  <div className="mt-0.5 text-xs text-muted">{fmt(b.period_start)} → {fmt(b.period_end)} · {t("budgets.plannedTotal", { amount: money(b.planned_total) })}</div>
                </div>
                <div className="flex items-center gap-1">
                  {approver && b.status === "draft" && <Button variant="outline" onClick={() => act(b.id, finance.approveBudget, t("budgets.approved"))} disabled={busy === b.id}><BadgeCheck size={15} />{t("budgets.approve")}</Button>}
                  {approver && b.status === "approved" && <Button variant="ghost" onClick={() => act(b.id, finance.reopenBudget, t("budgets.reopened"))} disabled={busy === b.id}><RotateCcw size={15} />{t("budgets.reopen")}</Button>}
                  <Button variant="ghost" onClick={() => setOpenId(openId === b.id ? null : b.id)} aria-expanded={openId === b.id}>{openId === b.id ? <ChevronUp size={15} /> : <ChevronDown size={15} />}{t("budgets.variance")}</Button>
                </div>
              </div>
              {openId === b.id && <VarianceTable budgetId={b.id} />}
            </div>
          ))}
        </div>
      )}
      <NewBudgetDrawer open={drawer} onClose={() => setDrawer(false)} categories={categories} onSaved={() => { load(); onChanged?.(); toast.success(t("budgets.created")); }} />
    </Card>
  );
}
