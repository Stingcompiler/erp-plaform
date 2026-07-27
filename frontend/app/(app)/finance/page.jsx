"use client";

import { useCallback, useEffect, useState } from "react";
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
  const [drawerOpen, setDrawerOpen] = useState(false);

  const money = (v) =>
    Number(v ?? 0).toLocaleString(language === "ar" ? "ar" : "en", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });

  const load = useCallback(() => {
    setLoading(true);
    finance.summary().then((r) => setSummary(r.data)).catch(() => setSummary(null));
    finance
      .expenses({ page: 1 })
      .then((r) => setExpenses(r.data.results))
      .catch(() => setExpenses([]))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (canRead("finance")) load();
  }, [canRead, load]);

  const dateFmt = (d) => (d ? new Date(d).toLocaleDateString(language === "ar" ? "ar" : "en") : "—");

  if (!canRead("finance")) {
    return (
      <div className="mx-auto mt-16 max-w-md rounded-card border border-line bg-surface p-8 text-center">
        <Lock className="mx-auto text-muted" />
        <h1 className="mt-3 font-display text-xl font-semibold">{t("shell.noAccessTitle")}</h1>
        <p className="mt-1 text-muted">{t("finance.noAccess")}</p>
      </div>
    );
  }

  const net = Number(summary?.net ?? 0);

  return (
    <div>
      <PageHeader
        title={t("finance.title")}
        subtitle={t("finance.subtitle")}
        actions={
          writable && (
            <Button onClick={() => setDrawerOpen(true)}>
              <Plus size={16} /> {t("finance.newExpense")}
            </Button>
          )
        }
      />

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 sm:gap-4">
        <StatTile label={t("finance.revenue")} value={money(summary?.revenue)} tone="ok" hint={t("finance.revenueHint")} />
        <StatTile label={t("finance.expenses")} value={money(summary?.expenses)} tone="danger" />
        <StatTile label={t("finance.net")} value={money(summary?.net)} tone={net < 0 ? "danger" : "ok"} />
      </div>

      <h2 className="mb-3 mt-6 font-display text-lg font-semibold text-ink">
        {t("finance.expensesTab")}
      </h2>

      {loading && <p className="py-8 text-center text-muted">{t("common.loading")}</p>}
      {!loading && expenses.length === 0 && (
        <Card className="p-8 text-center text-muted">{t("finance.noExpenses")}</Card>
      )}
      {!loading && expenses.length > 0 && (
        <Card>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-line text-xs uppercase tracking-wide text-muted">
                  <th className="px-4 py-3 text-start font-medium">{t("finance.category")}</th>
                  <th className="px-4 py-3 text-start font-medium">{t("finance.description")}</th>
                  <th className="px-4 py-3 text-start font-medium">{t("finance.method")}</th>
                  <th className="px-4 py-3 text-start font-medium">{t("finance.date")}</th>
                  <th className="px-4 py-3 text-end font-medium">{t("finance.amount")}</th>
                </tr>
              </thead>
              <tbody>
                {expenses.map((e) => (
                  <tr key={e.id} className="border-b border-line last:border-0">
                    <td className="px-4 py-3 text-ink">{e.category}</td>
                    <td className="px-4 py-3 text-muted">{e.description || "—"}</td>
                    <td className="px-4 py-3">
                      <Badge tone="muted">{e.method_display}</Badge>
                    </td>
                    <td className="tabular px-4 py-3 text-muted">{dateFmt(e.date)}</td>
                    <td className="tabular px-4 py-3 text-end text-ink">{money(e.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <ExpenseDrawer
        open={drawerOpen}
        writable={writable}
        onClose={() => setDrawerOpen(false)}
        onSaved={load}
      />
    </div>
  );
}
