"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Lock, Plus, ArrowUpRight, Receipt, Wallet, Scale } from "lucide-react";

import { finance } from "@/lib/api";
import { errorText } from "@/lib/errors";
import { useAuth } from "../../providers/AuthProvider";
import { useI18n } from "../../providers/I18nProvider";
import { useToast } from "@/components/ui/Toast";
import { Badge, Button, Card, Field, Input, PageHeader, Select } from "@/components/ui/kit";
import Drawer from "@/components/ui/Drawer";
import PaymentVerificationPanel from "@/components/finance/PaymentVerificationPanel";
import StatementReconcilePanel from "@/components/finance/StatementReconcilePanel";
import BudgetsPanel from "@/components/finance/BudgetsPanel";
import MoneyLedger from "@/components/finance/MoneyLedger";
import { SkeletonRows } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { expenseCategory } from "@/lib/expenseCategories";
import { localToday } from "@/lib/dates";
import { bankAccounts as bankAccountsApi } from "@/lib/api";
import BankAccounts from "@/components/sales/BankAccounts";
import { formatAmount } from "@/lib/money";
import { useMoney } from "@/lib/useMoney";
import { paymentMethodLabel } from "@/lib/labels";

function StatTile({ label, value, tone = "ink", icon: Icon }) {
  const toneClass = tone === "ok" ? "text-ok" : tone === "danger" ? "text-danger" : "text-ink";
  return (
    <Card className={`relative overflow-hidden p-4 sm:p-5 ${tone === "ok" ? "border-accent/30 bg-accent/5" : ""}`}>
      <div className="mb-3 flex items-center justify-between gap-2"><span className="text-sm font-medium text-muted">{label}</span><span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-paper text-accent"><Icon size={17} /></span></div>
      <div className={`tabular mt-1 break-words text-xl font-semibold sm:text-3xl ${toneClass}`}>{value}</div>
    </Card>
  );
}

function ExpenseDrawer({ open, writable, onClose, onSaved, categories = [] }) {
  const { t } = useI18n();
  const toast = useToast();
  const today = localToday();
  const EMPTY = { category: "", description: "", amount: "", method: "cash", date: today, company_bank_account: "", reverses: "" };
  const [form, setForm] = useState(EMPTY);
  const [saving, setSaving] = useState(false);
  const [accounts, setAccounts] = useState([]);
  const [recent, setRecent] = useState([]);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const negative = Number(form.amount) < 0;

  useEffect(() => {
    if (!open) return;
    setForm({ ...EMPTY, date: today });
    // A transfer names the account it left from (the bank balance subtracts
    // it); a negative amount corrects one of the recent expenses.
    bankAccountsApi.list().then((r) => setAccounts((r.data.results || r.data).filter((a) => a.is_active))).catch(() => setAccounts([]));
    finance.expenses({ page: 1, ordering: "-date" }).then((r) => setRecent((r.data.results || r.data).filter((e) => Number(e.amount) > 0))).catch(() => setRecent([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  async function save() {
    setSaving(true);
    try {
      const body = { ...form };
      if (body.method !== "bank_transfer" || !body.company_bank_account) delete body.company_bank_account;
      if (!negative || !body.reverses) delete body.reverses;
      await finance.createExpense(body);
      toast.success(t("common.save"));
      onSaved?.();
      onClose();
    } catch (err) {
      // The server says what is wrong (threshold, account, correction);
      // a generic "could not save" left the accountant with no way forward.
      toast.error(errorText(err, t, "finance.saveError"));
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
          <Input list="expense-categories" value={form.category} onChange={(e) => set("category", e.target.value)} />
          <datalist id="expense-categories">{categories.map((c) => <option key={c} value={c} />)}</datalist>
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
        {form.method === "bank_transfer" && (
          <Field label={t("finance.paidFromAccount")}>
            <Select value={form.company_bank_account} onChange={(e) => set("company_bank_account", e.target.value)}>
              <option value="">{t("common.choose")}</option>
              {accounts.map((a) => <option key={a.id} value={a.id}>{a.bank_name} · {a.account_name}</option>)}
            </Select>
          </Field>
        )}
        {negative && (
          <Field label={t("finance.correctsExpense")} hint={t("finance.correctsExpenseHint")}>
            <Select value={form.reverses} onChange={(e) => set("reverses", e.target.value)}>
              <option value="">{t("common.choose")}</option>
              {recent.map((e) => <option key={e.id} value={e.id}>{e.date} · {expenseCategory(e.category, t)} · {formatAmount(e.amount)}</option>)}
            </Select>
          </Field>
        )}
      </div>
    </Drawer>
  );
}

export default function FinancePage() {
  const { canRead, canWrite } = useAuth();
  const { t } = useI18n();
  const writable = canWrite("finance");
  const [categories, setCategories] = useState([]);
  const loadCategories = useCallback(() => {
    finance.categories().then((r) => setCategories(r.data)).catch(() => {});
  }, []);
  useEffect(() => { loadCategories(); }, [loadCategories]);
  const [reconcileKey, setReconcileKey] = useState(0);
  const [summary, setSummary] = useState(null);
  const [expenses, setExpenses] = useState([]);
  const [loading, setLoading] = useState(true);
  // "" when everything loaded; otherwise the sentence to show.
  const [error, setError] = useState("");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [page, setPage] = useState(1);
  const [count, setCount] = useState(0);
  const [next, setNext] = useState(false);
  const [filters, setFilters] = useState({ start: "", end: "", search: "", ordering: "-date", method: "standard" });
  const generation = useRef(0);
  const invalidDates = filters.start && filters.end && filters.start > filters.end;
  const { money: withCurrency } = useMoney();
  // Tiles: the figure with its currency, or a dash while it has not loaded.
  const money = (v) => withCurrency(v, { empty: "—" });
  // allSettled, not all: the totals and the expense list are two independent
  // requests, and one of them failing used to blank the other as well.
  const load = useCallback(async () => {
    const id = ++generation.current;
    setLoading(true); setError(""); setSummary(null);
    const [totals, rows] = await Promise.allSettled([
      finance.summary({ start: filters.start, end: filters.end, method: filters.method }),
      finance.expenses({ ...filters, page }),
    ]);
    if (id !== generation.current) return;
    if (totals.status === "fulfilled") setSummary(totals.value.data);
    if (rows.status === "fulfilled") {
      setExpenses(rows.value.data.results);
      setCount(rows.value.data.count); setNext(Boolean(rows.value.data.next));
    } else {
      setExpenses([]);
    }
    const failure = [totals, rows].find((r) => r.status === "rejected");
    setError(failure ? errorText(failure.reason, t, "improvements.loadError") : "");
    setLoading(false);
  }, [filters, page, t]);
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
    {error && <Card className="mb-4 p-4"><p role="alert" className="mb-3 text-danger">{error}</p><Button onClick={load}>{t("improvements.retry")}</Button></Card>}
    <div className="grid grid-cols-2 gap-3 xl:grid-cols-4" aria-busy={loading}>
      <StatTile label={t("finance.revenue")} value={money(summary?.revenue)} icon={ArrowUpRight} />
      <StatTile icon={Receipt} label={t("improvements.cogs")} value={money(summary?.cogs)} />
      <StatTile icon={Wallet} label={t("finance.expenses")} value={money(summary?.expenses)} />
      <StatTile icon={Scale} label={t("improvements.netProfit")} value={money(summary?.net)} tone={Number(summary?.net) < 0 ? "danger" : "ok"} />
    </div>
    <p className="mb-5 mt-3 text-xs text-muted">{t("improvements.revenueHint")} · {t("improvements.accountingNote")}</p>
    {/* The summary comes first; the verification worklist sits under it,
        folded to a count until someone opens it. */}
    {writable && <PaymentVerificationPanel refreshKey={reconcileKey} />}
    {writable && <StatementReconcilePanel onApplied={() => setReconcileKey((k) => k + 1)} />}
    <h2 className="mb-3 mt-6 font-display text-lg font-semibold">{t("finance.expensesTab")}</h2>
    <div className="mb-3 flex flex-wrap gap-3">
      <Field label={t("improvements.searchExpenses")}><Input type="search" value={filters.search} onChange={(e) => change("search",e.target.value)} /></Field>
      <Field label={t("improvements.sort")}><Select value={filters.ordering} onChange={(e) => change("ordering",e.target.value)}>
        <option value="-date">{t("improvements.newest")}</option><option value="date">{t("improvements.oldest")}</option><option value="-amount">{t("improvements.highest")}</option>
      </Select></Field>
    </div>
    {loading && !invalidDates && <SkeletonRows />}
    {!loading && !invalidDates && <Card>
      {expenses.length === 0 ? <EmptyState
        icon={Receipt}
        title={t("finance.emptyTitle")}
        body={t("finance.emptyBody")}
        filtered={Boolean(filters.search || filters.start || filters.end)}
        onClearFilters={() => { setFilters((f) => ({ ...f, search: "", start: "", end: "" })); setPage(1); }}
        action={writable && <Button onClick={() => setDrawerOpen(true)}><Plus size={16} />{t("finance.newExpense")}</Button>}
      /> :
      <div className="overflow-x-auto"><table className="stack-sm w-full text-sm"><thead><tr className="border-b border-line text-muted">
        {["category","description","method","date","amount"].map((key) => <th key={key} scope="col" className="px-4 py-3 text-start">{t(`finance.${key}`)}</th>)}
      </tr></thead><tbody>{expenses.map((e) => <tr key={e.id} className="border-b border-line last:border-0">
        <td className="px-4 py-3"><span className="inline-flex items-center gap-2">
          {expenseCategory(e.category, t)}
          {(e.payroll_run || e.salary_advance) && <Badge tone="accent">{t("finance.fromHr")}</Badge>}
        </span></td><td className="px-4 py-3">{e.description || "—"}</td>
        <td className="px-4 py-3"><Badge>{paymentMethodLabel(t, e.method)}</Badge></td>
        <td className="tabular whitespace-nowrap px-4 py-3">{e.date}</td><td className="tabular px-4 py-3">{formatAmount(e.amount)}</td>
      </tr>)}</tbody></table></div>}
      <div className="flex items-center justify-between gap-3 border-t border-line p-3">
        <Button variant="outline" disabled={page <= 1} onClick={() => setPage((p) => p-1)}>{t("improvements.previous")}</Button>
        <span className="text-sm text-muted">{t("improvements.page", {page,pages:Math.max(1,Math.ceil(count/50))})}</span>
        <Button variant="outline" disabled={!next} onClick={() => setPage((p) => p+1)}>{t("improvements.next")}</Button>
      </div>
    </Card>}
    <ExpenseDrawer open={drawerOpen} writable={writable} categories={categories} onClose={() => setDrawerOpen(false)} onSaved={() => { load(); loadCategories(); }} />
    <BudgetsPanel writable={writable} categories={categories} onChanged={loadCategories} />
    {/* Treasury belongs to finance: the accounts, their details and opening
        balances are managed here (the sales tab only reads them). */}
    {writable && <div className="mt-6"><BankAccounts writable={writable} /></div>}
    <MoneyLedger />
  </div>;
}
