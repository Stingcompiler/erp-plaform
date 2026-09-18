"use client";

import { useEffect, useState } from "react";

import { sales } from "@/lib/api";
import { useAuth } from "../../app/providers/AuthProvider";
import { useI18n } from "../../app/providers/I18nProvider";
import Drawer from "@/components/ui/Drawer";
import { Button, Field, Input } from "@/components/ui/kit";
import OpeningBalanceForm from "@/components/finance/OpeningBalanceForm";

const EMPTY = { name: "", phone: "", email: "", address: "", payment_terms_days: "", credit_limit: "", credit_hold: false };

/**
 * Create or edit a customer. Until this drawer existed customers could only
 * be born by converting a CRM lead, and nobody could set credit terms.
 * Credit limit / hold are a manager's call (the API refuses them otherwise),
 * so they only show to a user who may approve.
 */
export default function CustomerDrawer({ open, onClose, customer, onSaved }) {
  const { t } = useI18n();
  const { can } = useAuth();
  const managesCredit = can("finance.approve");
  const [form, setForm] = useState(EMPTY);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setError("");
    setForm(customer ? {
      name: customer.name || "", phone: customer.phone || "", email: customer.email || "",
      address: customer.address || "",
      payment_terms_days: customer.payment_terms_days ?? "",
      credit_limit: customer.credit_limit ?? "", credit_hold: Boolean(customer.credit_hold),
    } : EMPTY);
  }, [open, customer]);

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.type === "checkbox" ? e.target.checked : e.target.value }));

  async function save() {
    setError("");
    if (!form.name.trim()) return setError(t("customers.nameRequired"));
    const body = {
      name: form.name.trim(), phone: form.phone.trim(), email: form.email.trim(), address: form.address.trim(),
      payment_terms_days: form.payment_terms_days === "" ? null : Number(form.payment_terms_days),
    };
    if (managesCredit) {
      body.credit_limit = form.credit_limit === "" ? null : form.credit_limit;
      body.credit_hold = form.credit_hold;
    }
    setBusy(true);
    try {
      const r = customer ? await sales.updateCustomer(customer.id, body) : await sales.createCustomer(body);
      onSaved?.(r.data);
      onClose();
    } catch (err) {
      const data = err?.response?.data;
      setError(typeof data === "object" && data ? Object.values(data).flat().join(" ") : t("customers.saveError"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={customer ? t("customers.editTitle") : t("customers.newTitle")}
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>{t("common.cancel")}</Button>
          <Button onClick={save} disabled={busy}>{busy ? t("common.saving") : t("common.save")}</Button>
        </div>
      }
    >
      <div className="space-y-4">
        <Field label={t("customers.name")}>
          <Input value={form.name} onChange={set("name")} autoFocus />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t("customers.phone")}>
            <Input value={form.phone} onChange={set("phone")} inputMode="tel" dir="ltr" />
          </Field>
          <Field label={t("customers.email")}>
            <Input value={form.email} onChange={set("email")} type="email" dir="ltr" />
          </Field>
        </div>
        <Field label={t("customers.address")}>
          <Input value={form.address} onChange={set("address")} />
        </Field>
        <Field label={t("customers.terms")} hint={t("customers.termsHint")}>
          <Input type="number" inputMode="numeric" min="0" max="365" value={form.payment_terms_days} onChange={set("payment_terms_days")} placeholder={t("customers.termsDefault")} className="w-32" />
        </Field>
        {managesCredit && (
          <div className="rounded-card border border-line bg-paper/50 p-3">
            <div className="text-sm font-semibold">{t("customers.creditSection")}</div>
            <p className="mt-0.5 text-xs text-muted">{t("customers.creditHint")}</p>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <Field label={t("customers.creditLimit")}>
                <Input type="number" inputMode="decimal" min="0" step="0.01" value={form.credit_limit} onChange={set("credit_limit")} placeholder={t("customers.noLimit")} />
              </Field>
              <label className="flex items-center gap-2 self-end pb-2 text-sm">
                <input type="checkbox" checked={form.credit_hold} onChange={set("credit_hold")} className="h-4 w-4 accent-accent" />
                {t("customers.creditHold")}
              </label>
            </div>
          </div>
        )}
        {customer?.id && <OpeningBalanceForm kind="customer" account={customer} onSaved={onSaved} />}
        {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      </div>
    </Drawer>
  );
}
