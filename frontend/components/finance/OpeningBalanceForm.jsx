"use client";

import { useState } from "react";
import { Scale } from "lucide-react";

import { purchasing, sales } from "@/lib/api";
import { useAuth } from "../../app/providers/AuthProvider";
import { useI18n } from "../../app/providers/I18nProvider";
import { useToast } from "@/components/ui/Toast";
import { Badge, Button, Field, Input } from "@/components/ui/kit";

const money = (v) =>
  Number(v ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const today = () => new Date().toISOString().slice(0, 10);

/**
 * The balance an account already carried when the books started here.
 * Recorded as a document (a line-less invoice / a receipt-less bill) so the
 * ledger, aging, statements and collection all see it; shown once recorded.
 * Approver-only, like credit terms.
 */
export default function OpeningBalanceForm({ kind, account, onSaved }) {
  const { t, language } = useI18n();
  const { can } = useAuth();
  const toast = useToast();
  const [amount, setAmount] = useState("");
  const [asOf, setAsOf] = useState(today);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const approver = can("finance.approve");
  const existing = account?.opening_balance;

  if (!account?.id || (!existing && !approver)) return null;

  async function save() {
    setError("");
    setBusy(true);
    try {
      const call = kind === "supplier" ? purchasing.supplierOpeningBalance : sales.customerOpeningBalance;
      await call(account.id, { amount, as_of: asOf, note });
      toast.success(t("openingBalance.saved"));
      onSaved?.();
    } catch (err) {
      const data = err?.response?.data;
      setError((data && (data.detail || Object.values(data).flat().join(" "))) || t("openingBalance.error"));
    } finally {
      setBusy(false);
    }
  }

  const fmt = (d) => new Date(`${d}T00:00:00`).toLocaleDateString(language === "ar" ? "ar" : "en");

  return (
    <div className="rounded-control border border-line bg-paper p-3">
      <div className="flex items-center gap-2 text-sm font-semibold"><Scale size={15} className="text-accent" />{t("openingBalance.title")}</div>
      {existing ? (
        <p className="mt-2 text-sm">
          <span className="tabular font-medium">{money(existing.amount)}</span>
          <span className="text-muted"> · {t("openingBalance.asOf", { date: fmt(existing.as_of) })}</span>
          {existing.number && <Badge tone="muted">{existing.number}</Badge>}
          <span className="mt-1 block text-xs text-muted">{kind === "supplier" ? t("openingBalance.correctSupplier") : t("openingBalance.correctCustomer")}</span>
        </p>
      ) : (
        <>
          <p className="mt-0.5 text-xs text-muted">{kind === "supplier" ? t("openingBalance.hintSupplier") : t("openingBalance.hintCustomer")}</p>
          <div className="mt-3 grid gap-3 sm:grid-cols-3">
            <Field label={t("openingBalance.amount")}>
              <Input type="number" inputMode="decimal" min="0.01" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} className="text-end" />
            </Field>
            <Field label={t("openingBalance.asOfLabel")}>
              <Input type="date" value={asOf} max={today()} onChange={(e) => setAsOf(e.target.value)} />
            </Field>
            <Field label={t("openingBalance.note")}>
              <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder={t("openingBalance.notePlaceholder")} />
            </Field>
          </div>
          {error && <p role="alert" className="mt-2 text-sm text-danger">{error}</p>}
          <div className="mt-3 flex justify-end">
            <Button variant="outline" onClick={save} disabled={busy || !(Number(amount) > 0) || !asOf}>{busy ? t("common.saving") : t("openingBalance.record")}</Button>
          </div>
        </>
      )}
    </div>
  );
}
