"use client";

import { useCallback, useEffect, useState } from "react";
import { Plus } from "lucide-react";

import { bankAccounts as api } from "@/lib/api";
import { useI18n } from "../../app/providers/I18nProvider";
import Drawer from "@/components/ui/Drawer";
import { Badge, Button, Card, Field, Input } from "@/components/ui/kit";

const EMPTY = { bank_name: "", account_name: "", account_number: "" };

function AccountForm({ open, onClose, onSaved }) {
  const { t } = useI18n();
  const [form, setForm] = useState(EMPTY);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  async function save() {
    setError("");
    setSaving(true);
    try {
      await api.create(form);
      setForm(EMPTY);
      onSaved();
      onClose();
    } catch (err) {
      const data = err?.response?.data;
      setError(
        typeof data === "object" && data ? Object.values(data).flat().join(" ") : t("purchasing.saveError")
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={t("sales.newBankAccount")}
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button onClick={save} disabled={saving || !form.bank_name || !form.account_name}>
            {saving ? t("common.saving") : t("common.add")}
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        <Field label={t("sales.bankName")}>
          <Input value={form.bank_name} onChange={set("bank_name")} />
        </Field>
        <Field label={t("sales.accountName")}>
          <Input value={form.account_name} onChange={set("account_name")} />
        </Field>
        <Field label={t("sales.accountNumber")}>
          <Input value={form.account_number} onChange={set("account_number")} />
        </Field>
        {error && <p className="text-sm text-danger">{error}</p>}
      </div>
    </Drawer>
  );
}

export default function BankAccounts({ writable, onChanged }) {
  const { t } = useI18n();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    api
      .list()
      .then((r) => setRows(r.data.results || r.data))
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div>
      <div className="mb-4 flex justify-end">
        {writable && (
          <Button onClick={() => setOpen(true)}>
            <Plus size={16} /> {t("sales.newBankAccount")}
          </Button>
        )}
      </div>
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line text-xs uppercase tracking-wide text-muted">
                <th className="px-4 py-3 text-start font-medium">{t("sales.bankName")}</th>
                <th className="px-4 py-3 text-start font-medium">{t("sales.accountName")}</th>
                <th className="px-4 py-3 text-start font-medium">{t("sales.accountNumber")}</th>
                <th className="px-4 py-3 text-end font-medium">{t("common.status")}</th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr>
                  <td colSpan={4} className="px-4 py-8 text-center text-muted">
                    {t("common.loading")}
                  </td>
                </tr>
              )}
              {!loading && rows.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-8 text-center text-muted">
                    {t("sales.noBankAccounts")}
                  </td>
                </tr>
              )}
              {!loading &&
                rows.map((a) => (
                  <tr key={a.id} className="border-b border-line last:border-0">
                    <td className="px-4 py-3 text-ink">{a.bank_name}</td>
                    <td className="px-4 py-3 text-muted">{a.account_name}</td>
                    <td className="tabular px-4 py-3 text-muted">{a.account_number || "—"}</td>
                    <td className="px-4 py-3 text-end">
                      <label className="me-3 inline-flex items-center gap-1 text-xs text-muted" title={t("sales.showToCustomersHint")}>
                        <input type="checkbox" checked={Boolean(a.show_to_customers)} disabled={!writable}
                          onChange={async (e) => { try { await api.update(a.id, { show_to_customers: e.target.checked }); load(); } catch { /* keep */ } }} />
                        {t("sales.showToCustomers")}
                      </label>
                      {a.is_active ? <Badge tone="ok">{t("common.active")}</Badge> : <Badge tone="muted">{t("common.inactive")}</Badge>}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </Card>
      <AccountForm
        open={open}
        onClose={() => setOpen(false)}
        onSaved={() => {
          load();
          onChanged?.();
        }}
      />
    </div>
  );
}
