"use client";

import { useEffect, useState } from "react";

import { bankAccounts as bankApi, cashShifts, sales } from "@/lib/api";
import { useI18n } from "../../app/providers/I18nProvider";
import Drawer from "@/components/ui/Drawer";
import { Button, Field, Input, Select } from "@/components/ui/kit";

const money = (v) =>
  Number(v ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/**
 * Hand money back against a credit note.
 *
 * A return on a paid invoice leaves the customer in credit; this is the
 * document that settles it. Cash comes out of the caller's open drawer (the
 * server writes the drawer movement), a transfer names the paying account.
 * The server caps the total refunded at the note's amount.
 */
export default function RefundDrawer({ note, open, onClose, onDone }) {
  const { t } = useI18n();
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState("cash");
  const [account, setAccount] = useState("");
  const [reference, setReference] = useState("");
  const [accounts, setAccounts] = useState([]);
  const [shift, setShift] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open || !note) return;
    setAmount(String(note.remaining_refundable ?? note.amount ?? ""));
    setMethod("cash"); setAccount(""); setReference(""); setError("");
    bankApi.list().then((r) => setAccounts(r.data.results || r.data)).catch(() => setAccounts([]));
    cashShifts.current().then((r) => setShift(r.data?.shift ?? r.data ?? null)).catch(() => setShift(null));
  }, [open, note]);

  if (!note) return null;

  async function go() {
    setError("");
    const body = { credit_note: note.id, amount, method, client_uuid: crypto.randomUUID() };
    if (method === "cash") {
      if (!shift?.id) { setError(t("corrections.needOpenDrawer")); return; }
      body.shift = shift.id;
    } else {
      if (!account || reference.length !== 4) { setError(t("corrections.needBankDetails")); return; }
      body.company_bank_account = Number(account);
      body.reference_last4 = reference;
    }
    setBusy(true);
    try {
      await sales.createRefund(body);
      onDone?.();
      onClose();
    } catch (err) {
      const data = err?.response?.data;
      setError(
        typeof data === "object" && data ? Object.values(data).flat().join(" ") : t("corrections.failed")
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={t("corrections.refund")}
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>{t("common.cancel")}</Button>
          <Button onClick={go} disabled={busy || !amount}>
            {busy ? t("common.saving") : t("corrections.recordRefund")}
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        <div className="rounded-card border border-line p-3 text-sm">
          <div className="flex justify-between">
            <span className="text-muted">{t("doc.number")}</span>
            <span className="tabular text-ink">{note.number_display}</span>
          </div>
          <div className="mt-1 flex justify-between">
            <span className="text-muted">{t("corrections.remainingRefundable")}</span>
            <span className="tabular text-ink">{money(note.remaining_refundable)}</span>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("common.method")}>
            <Select value={method} onChange={(e) => setMethod(e.target.value)}>
              <option value="cash">{t("common.cash")}</option>
              <option value="bank_transfer">{t("common.bankTransfer")}</option>
            </Select>
          </Field>
          <Field label={t("common.amount")}>
            <Input type="number" step="0.01" min="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} />
          </Field>
        </div>
        {method === "cash" && (
          <p className="text-xs text-muted">
            {shift?.id ? t("corrections.fromOpenDrawer") : t("corrections.needOpenDrawer")}
          </p>
        )}
        {method === "bank_transfer" && (
          <div className="grid grid-cols-2 gap-3">
            <Field label={t("purchasing.fromAccount")}>
              <Select value={account} onChange={(e) => setAccount(e.target.value)}>
                <option value="">{t("common.select")}</option>
                {accounts.map((a) => (
                  <option key={a.id} value={a.id}>{a.bank_name}</option>
                ))}
              </Select>
            </Field>
            <Field label={t("sales.refLast4")}>
              <Input value={reference} maxLength={4} onChange={(e) => setReference(e.target.value.replace(/\D/g, "").slice(0, 4))} />
            </Field>
          </div>
        )}
        {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      </div>
    </Drawer>
  );
}
