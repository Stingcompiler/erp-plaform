"use client";

import { useEffect, useState } from "react";

import { purchasing } from "@/lib/api";
import { useI18n } from "../../app/providers/I18nProvider";
import Drawer from "@/components/ui/Drawer";
import { Button, Field, Input, Select } from "@/components/ui/kit";
import { errorText } from "@/lib/errors";
import { round2 } from "@/lib/money";
import { useStableIds } from "@/lib/useStableIds";

/**
 * Records a supplier's invoice (a bill).
 *
 * Nothing created bills before this: the API accepted them, but no screen
 * posted one and receiving stock doesn't raise one either, so the Bills tab was
 * permanently empty and there was nothing to pay against.
 *
 * Tax is entered rather than computed from the company's rate: this is the
 * *supplier's* document, and what they charged is a fact to be recorded, not a
 * figure for us to recalculate.
 */
const EMPTY = {
  supplier: "",
  supplier_invoice_number: "",
  subtotal: "",
  tax_amount: "",
  payment_terms_days: "0",
};

export default function NewBillDrawer({ open, onClose, onSaved, suppliers }) {
  const { t } = useI18n();
  const [form, setForm] = useState(EMPTY);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const { idFor, reset } = useStableIds();

  useEffect(() => {
    setForm(EMPTY);
    setError("");
    reset();
  }, [open, reset]);

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  // Rounded to cents like the server: 100.10 + 15.02 summed in floating
  // point is 115.11999999999999, which the API refused as "too many digits".
  const subtotal = round2(form.subtotal);
  const tax = round2(form.tax_amount);
  const total = round2(subtotal + tax);

  async function save() {
    setError("");
    if (!form.supplier) {
      setError(t("purchasing.chooseSupplier"));
      return;
    }
    if (!(total > 0)) {
      setError(t("purchasing.billTotalRequired"));
      return;
    }
    setSaving(true);
    try {
      await purchasing.createBill({
        // One key per bill being entered: a retry after a timeout replays
        // the same bill instead of creating a second one.
        client_uuid: idFor(),
        supplier: Number(form.supplier),
        supplier_invoice_number: form.supplier_invoice_number.trim(),
        subtotal: subtotal.toFixed(2),
        tax_amount: tax.toFixed(2),
        total: total.toFixed(2),
        payment_terms_days: Number(form.payment_terms_days || 0),
      });
      onSaved();
      onClose();
    } catch (err) {
      setError(errorText(err, t, "purchasing.saveError"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={t("purchasing.newBill")}
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button onClick={save} disabled={saving}>
            {saving ? t("common.saving") : t("purchasing.saveBill")}
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        <Field label={t("purchasing.supplier")}>
          <Select value={form.supplier} onChange={set("supplier")}>
            <option value="">{t("common.select")}</option>
            {(suppliers || []).map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </Select>
        </Field>

        <Field
          label={t("purchasing.supplierInvoiceNo")}
          hint={t("purchasing.supplierInvoiceNoHint")}
        >
          <Input
            value={form.supplier_invoice_number}
            onChange={set("supplier_invoice_number")}
          />
        </Field>

        <div className="grid grid-cols-2 gap-3">
          <Field label={t("doc.subtotal")}>
            <Input type="number" value={form.subtotal} onChange={set("subtotal")} />
          </Field>
          <Field label={t("doc.tax")}>
            <Input
              type="number"
              value={form.tax_amount}
              onChange={set("tax_amount")}
            />
          </Field>
        </div>

        <Field
          label={t("purchasing.paymentTerms")}
          hint={t("purchasing.paymentTermsHint")}
        >
          <Input
            type="number"
            value={form.payment_terms_days}
            onChange={set("payment_terms_days")}
          />
        </Field>

        <div className="flex items-center justify-between rounded-card border border-line bg-paper px-3 py-2">
          <span className="text-sm text-muted">{t("doc.total")}</span>
          <span className="tabular text-lg font-medium text-ink">
            {total.toLocaleString(undefined, {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })}
          </span>
        </div>

        {error && <p className="text-sm text-danger">{error}</p>}
      </div>
    </Drawer>
  );
}
