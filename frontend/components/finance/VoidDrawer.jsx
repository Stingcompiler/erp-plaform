"use client";

import { useEffect, useState } from "react";

import { bankAccounts as bankApi, cashShifts } from "@/lib/api";
import { useI18n } from "../../app/providers/I18nProvider";
import Drawer from "@/components/ui/Drawer";
import { Button, Field, Input, Select } from "@/components/ui/kit";

const money = (v) =>
  Number(v ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/**
 * Cancel a financial document by an offsetting entry (Rule #9).
 *
 * The server never edits the row: an invoice gets a full credit note, a
 * reversal of its stock movements and — when anything was paid — a refund
 * document for the money handed back. This drawer collects the reason and,
 * when `paidAmount` is above zero, how the refund goes out: cash from the
 * caller's open drawer, or a transfer from one of the company's accounts.
 */
export default function VoidDrawer({ open, onClose, onDone, title, summary, paidAmount = 0, submit }) {
  const { t } = useI18n();
  const [reason, setReason] = useState("");
  const [method, setMethod] = useState("cash");
  const [account, setAccount] = useState("");
  const [reference, setReference] = useState("");
  const [accounts, setAccounts] = useState([]);
  const [shift, setShift] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const needsRefund = Number(paidAmount) > 0;

  useEffect(() => {
    if (!open) return;
    setReason(""); setMethod("cash"); setAccount(""); setReference(""); setError("");
    if (!needsRefund) return;
    bankApi.list().then((r) => setAccounts(r.data.results || r.data)).catch(() => setAccounts([]));
    cashShifts.current().then((r) => setShift(r.data?.shift ?? r.data ?? null)).catch(() => setShift(null));
  }, [open, needsRefund]);

  async function go() {
    setError("");
    if (!reason.trim()) { setError(t("corrections.reasonRequired")); return; }
    const body = { reason: reason.trim() };
    if (needsRefund) {
      if (method === "cash") {
        if (!shift?.id) { setError(t("corrections.needOpenDrawer")); return; }
        body.refund = { method: "cash", shift: shift.id };
      } else {
        if (!account || reference.length !== 4) { setError(t("corrections.needBankDetails")); return; }
        body.refund = { method: "bank_transfer", company_bank_account: Number(account), reference_last4: reference };
      }
    }
    setBusy(true);
    try {
      await submit(body);
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
      title={title}
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>{t("common.cancel")}</Button>
          <Button variant="danger" onClick={go} disabled={busy}>
            {busy ? t("common.saving") : t("corrections.confirmVoid")}
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        {summary && <div className="rounded-card border border-line p-3 text-sm text-ink">{summary}</div>}
        <p className="text-sm text-muted">{t("corrections.voidExplain")}</p>
        <Field label={t("corrections.reason")}>
          <Input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={255} autoFocus />
        </Field>
        {needsRefund && (
          <div className="space-y-3 rounded-card border border-line p-3">
            <div className="flex justify-between text-sm">
              <span className="text-muted">{t("corrections.toRefund")}</span>
              <span className="tabular text-ink">{money(paidAmount)}</span>
            </div>
            <Field label={t("common.method")}>
              <Select value={method} onChange={(e) => setMethod(e.target.value)}>
                <option value="cash">{t("common.cash")}</option>
                <option value="bank_transfer">{t("common.bankTransfer")}</option>
              </Select>
            </Field>
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
          </div>
        )}
        {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      </div>
    </Drawer>
  );
}
