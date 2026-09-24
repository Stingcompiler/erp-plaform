"use client";

import { useEffect, useState } from "react";

import { purchasing } from "@/lib/api";
import { useI18n } from "../../app/providers/I18nProvider";
import Drawer from "@/components/ui/Drawer";
import { Button, Field, Input, Select } from "@/components/ui/kit";
import { errorText } from "@/lib/errors";
import { round2 } from "@/lib/money";
import { useStableIds } from "@/lib/useStableIds";
import {
  AmountWithBase, CurrencyFields, EMPTY_FX, fxCurrency, fxPayload, fxProblem, fxRate,
  usePurchaseCurrencies,
} from "@/components/purchasing/PurchaseCurrency";

const money = (v) =>
  Number(v ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

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
 *
 * Linking the goods receipt it bills (three-way match) lets the server check
 * the bill against what arrived and refuse a second bill for the same goods;
 * the bill then takes the receipt's currency and rate.
 */
const EMPTY = {
  supplier: "",
  goods_receipt: "",
  supplier_invoice_number: "",
  subtotal: "",
  tax_amount: "",
  payment_terms_days: "0",
};

export default function NewBillDrawer({ open, onClose, onSaved, suppliers }) {
  const { t, language } = useI18n();
  const [form, setForm] = useState(EMPTY);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const { idFor, reset } = useStableIds();
  const fxInfo = usePurchaseCurrencies();
  const [fx, setFx] = useState(EMPTY_FX);
  // The chosen supplier's receipts that have no live bill yet.
  const [receipts, setReceipts] = useState([]);

  useEffect(() => {
    setForm(EMPTY);
    setFx(EMPTY_FX);
    setError("");
    reset();
  }, [open, reset]);

  useEffect(() => {
    setReceipts([]);
    if (!open || !form.supplier) return undefined;
    let live = true;
    purchasing
      .goodsReceipts({ supplier: form.supplier, unbilled: 1, page_size: 100 })
      .then((r) => { if (live) setReceipts(r.data.results ?? r.data); })
      .catch(() => {});
    return () => { live = false; };
  }, [open, form.supplier]);

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));
  const receipt = receipts.find((r) => String(r.id) === form.goods_receipt) || null;

  function pickSupplier(e) {
    const supplier = e.target.value;
    setForm((f) => ({ ...f, supplier, goods_receipt: "" }));
  }

  function pickReceipt(e) {
    const id = e.target.value;
    const chosen = receipts.find((r) => String(r.id) === id);
    // Prefilled with what was received; the supplier's own figure is typed
    // over it if it differs, and the server checks the gap.
    setForm((f) => ({ ...f, goods_receipt: id, subtotal: chosen ? String(chosen.received_value) : f.subtotal }));
  }

  // Rounded to cents like the server: 100.10 + 15.02 summed in floating
  // point is 115.11999999999999, which the API refused as "too many digits".
  const subtotal = round2(form.subtotal);
  const tax = round2(form.tax_amount);
  const total = round2(subtotal + tax);
  const currency = receipt ? receipt.currency || fxInfo.currency : fxCurrency(fx, fxInfo);
  const rate = receipt ? Number(receipt.exchange_rate) || 1 : fxRate(fx, fxInfo);
  const fmtDate = (d) => (d ? new Date(d).toLocaleDateString(language === "ar" ? "ar" : "en") : "");

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
    const fxError = receipt ? "" : fxProblem(fx, fxInfo, t);
    if (fxError) {
      setError(fxError);
      return;
    }
    setSaving(true);
    try {
      await purchasing.createBill({
        // One key per bill being entered: a retry after a timeout replays
        // the same bill instead of creating a second one.
        client_uuid: idFor(),
        supplier: Number(form.supplier),
        ...(receipt
          ? {
              goods_receipt: receipt.id,
              ...(receipt.purchase_order ? { purchase_order: receipt.purchase_order } : {}),
            }
          : fxPayload(fx, fxInfo)),
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
          <Select value={form.supplier} onChange={pickSupplier}>
            <option value="">{t("common.select")}</option>
            {(suppliers || []).map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </Select>
        </Field>

        {form.supplier && (
          <Field
            label={t("purchasing.receipt.label")}
            hint={receipts.length ? t("purchasing.receipt.hint") : t("purchasing.receipt.noneOpen")}
          >
            <Select value={form.goods_receipt} onChange={pickReceipt} disabled={!receipts.length}>
              <option value="">{t("purchasing.receipt.none")}</option>
              {receipts.map((r) => (
                <option key={r.id} value={r.id}>
                  {t("purchasing.receipt.option", {
                    id: String(r.id).padStart(5, "0"),
                    date: fmtDate(r.received_at),
                    amount: money(r.received_value),
                    currency: r.currency || fxInfo.currency,
                  })}
                </option>
              ))}
            </Select>
          </Field>
        )}

        <CurrencyFields
          info={fxInfo}
          fx={fx}
          onChange={setFx}
          locked={receipt ? { currency: receipt.currency, rate: receipt.exchange_rate, source: "receipt" } : null}
        />

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
          <AmountWithBase
            className="text-lg font-medium text-ink"
            amount={total}
            currency={currency}
            rate={rate}
            info={fxInfo}
          />
        </div>

        {error && <p className="text-sm text-danger">{error}</p>}
      </div>
    </Drawer>
  );
}
