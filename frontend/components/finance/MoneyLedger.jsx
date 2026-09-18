"use client";

import { useCallback, useEffect, useState } from "react";
import { BadgeCheck, FileText, Landmark } from "lucide-react";

import { purchasing, sales } from "@/lib/api";
import { useAuth } from "../../app/providers/AuthProvider";
import { useI18n } from "../../app/providers/I18nProvider";
import { useToast } from "@/components/ui/Toast";
import DocumentDrawer from "@/components/print/DocumentDrawer";
import TabBar from "@/components/ui/TabBar";
import { Badge, Button, Card, Select } from "@/components/ui/kit";

const money = (v) =>
  Number(v ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const SOURCES = {
  payments: { list: (p) => sales.payments(p), doc: sales.paymentDocument, out: false },
  refunds: { list: (p) => sales.refunds(p), doc: sales.refundDocument, out: true },
  supplier: { list: (p) => purchasing.supplierPayments(p), doc: purchasing.supplierPaymentDocument, out: true },
};

/**
 * Every money movement in one place: customer payments, refunds handed back,
 * and supplier payments. The three lists existed as endpoints (and printable
 * vouchers) but the screens only ever showed the unverified worklist, so a
 * treasurer could not answer "what went out on Tuesday" without the database.
 */
export default function MoneyLedger({ refreshKey }) {
  const { t, language } = useI18n();
  const { canWrite } = useAuth();
  const toast = useToast();
  const canVerify = canWrite("finance") || canWrite("purchasing");
  const [tab, setTab] = useState("payments");
  const [method, setMethod] = useState("");
  const [rows, setRows] = useState(null);
  const [doc, setDoc] = useState(null);
  const [busy, setBusy] = useState(null);

  const load = useCallback(() => {
    setRows(null);
    const params = { page_size: 50 };
    if (method) params.method = method;
    SOURCES[tab].list(params).then((r) => setRows(r.data.results ?? r.data)).catch(() => setRows([]));
  }, [tab, method]);
  useEffect(() => { load(); }, [load, refreshKey]);

  async function verify(row) {
    setBusy(row.id);
    try {
      await purchasing.verifySupplierPayment(row.id);
      toast.success(t("finance.ledger.verified"));
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || t("finance.verifyError"));
    } finally { setBusy(null); }
  }

  const fmt = (v) => (v ? new Date(v).toLocaleString(language === "ar" ? "ar" : "en", { dateStyle: "medium", timeStyle: "short" }) : "—");
  const who = (r) => (tab === "payments" ? r.customer_name : tab === "refunds" ? r.customer_name : r.supplier_name) || "—";
  const ref = (r) => (tab === "payments" ? r.invoice_number : tab === "refunds" ? r.credit_note_number : r.bill_number) || "—";
  const bank = (r) => r.bank_account_name || r.from_bank_account_name;

  return (
    <Card className="mt-5">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line p-4">
        <h2 className="flex items-center gap-2 font-display text-lg font-semibold"><Landmark size={18} className="text-accent" />{t("finance.ledger.title")}</h2>
        <div className="w-40">
          <Select value={method} onChange={(e) => setMethod(e.target.value)} aria-label={t("finance.ledger.method")}>
            <option value="">{t("finance.ledger.allMethods")}</option>
            <option value="cash">{t("finance.ledger.cash")}</option>
            <option value="bank_transfer">{t("finance.ledger.bank")}</option>
            {tab === "payments" && <option value="credit">{t("finance.ledger.storeCredit")}</option>}
          </Select>
        </div>
      </div>
      <div className="px-4 pt-3">
        <TabBar value={tab} onChange={setTab} tabs={[
          { id: "payments", label: t("finance.ledger.payments") },
          { id: "refunds", label: t("finance.ledger.refunds") },
          { id: "supplier", label: t("finance.ledger.supplierPayments") },
        ]} />
      </div>
      {rows === null ? <p className="p-8 text-center text-muted">{t("common.loading")}</p> : rows.length === 0 ? (
        <p className="p-8 text-center text-muted">{t("finance.ledger.empty")}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-line text-xs uppercase tracking-wide text-muted">
              <th className="px-3 py-2 text-start font-medium">{t("finance.ledger.when")}</th>
              <th className="px-3 py-2 text-start font-medium">{tab === "supplier" ? t("finance.ledger.supplier") : t("finance.ledger.customer")}</th>
              <th className="px-3 py-2 text-start font-medium">{t("finance.ledger.reference")}</th>
              <th className="px-3 py-2 text-start font-medium">{t("finance.ledger.method")}</th>
              <th className="px-3 py-2 text-end font-medium">{t("finance.ledger.amount")}</th>
              <th className="px-3 py-2 text-start font-medium">{t("finance.ledger.people")}</th>
              <th className="px-3 py-2" />
            </tr></thead>
            <tbody>{rows.map((r) => (
              <tr key={r.id} className="border-b border-line last:border-0">
                <td className="px-3 py-2 whitespace-nowrap">{fmt(r.recorded_at)}</td>
                <td className="px-3 py-2">{who(r)}</td>
                <td className="px-3 py-2 text-muted">{ref(r)}</td>
                <td className="px-3 py-2"><div>{r.method === "cash" ? t("finance.ledger.cash") : r.method === "credit" ? t("finance.ledger.storeCredit") : t("finance.ledger.bank")}</div>{bank(r) && <div className="text-xs text-muted">{bank(r)}{r.reference_last4 ? ` · ${r.reference_last4}` : ""}</div>}{r.credit_note_number && <div className="text-xs text-muted">{r.credit_note_number}</div>}</td>
                <td className={`tabular px-3 py-2 text-end font-medium ${SOURCES[tab].out ? "text-danger" : "text-ok"}`}>{SOURCES[tab].out ? "−" : "+"}{money(r.amount)}{r.currency && r.currency !== "SDG" ? ` ${r.currency}` : ""}</td>
                <td className="px-3 py-2 text-xs text-muted">
                  <div>{t("finance.recordedByName", { name: r.recorded_by_name || "—" })}</div>
                  {tab !== "refunds" && r.method !== "credit" && (r.verified_at ? <Badge tone="ok">{t("finance.ledger.verifiedBy", { name: r.verified_by_name || "—" })}</Badge> : <Badge tone="warn">{t("finance.ledger.unverified")}</Badge>)}
                </td>
                <td className="px-3 py-2 text-end whitespace-nowrap">
                  {tab === "supplier" && canVerify && !r.verified_at && (
                    <Button variant="outline" className="me-1" onClick={() => verify(r)} disabled={busy === r.id}><BadgeCheck size={15} />{t("finance.verify")}</Button>
                  )}
                  <Button variant="ghost" onClick={() => setDoc(r.id)} aria-label={t("finance.ledger.voucher")}><FileText size={15} /></Button>
                </td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
      <DocumentDrawer open={doc !== null} onClose={() => setDoc(null)} fetcher={SOURCES[tab].doc} id={doc} title={t("finance.ledger.voucher")} />
    </Card>
  );
}
