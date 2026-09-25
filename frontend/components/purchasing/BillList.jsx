"use client";

import { useCallback, useEffect, useState } from "react";
import { FileText, Plus } from "lucide-react";

import { purchasing } from "@/lib/api";
import { useAuth } from "../../app/providers/AuthProvider";
import { useI18n } from "../../app/providers/I18nProvider";
import { useOfflineMutation } from "@/components/sync/useOfflineMutation";
import VoidDrawer from "@/components/finance/VoidDrawer";
import Drawer from "@/components/ui/Drawer";
import { Badge, Button, Card, Field, Input, Select } from "@/components/ui/kit";
import { errorText } from "@/lib/errors";
import { SkeletonTableRows } from "@/components/ui/Skeleton";
import { EmptyTableRow } from "@/components/ui/EmptyState";
import { useStableIds } from "@/lib/useStableIds";
import { AmountWithBase, usePurchaseCurrencies } from "@/components/purchasing/PurchaseCurrency";
import { formatAmount } from "@/lib/money";

const money = (v) =>
  formatAmount(v);

// A bill settles in its own currency (a USD bill is paid in USD); the
// company-currency figure sits under it.
function BillAmount({ bill, amount, info }) {
  return (
    <AmountWithBase
      amount={amount}
      currency={bill.currency || info.currency}
      rate={bill.exchange_rate}
      info={info}
    />
  );
}

// The statuses the server sends (Bill.status). The keys used to be
// partial/unpaid, which it never sends, so an unpaid bill showed grey.
const statusTone = { paid: "ok", partially_paid: "warn", open: "danger", void: "muted" };

function PaymentDrawer({ bill, supplierName, bankAccounts, open, onClose, onPaid }) {
  const { idFor, reset } = useStableIds();
  const { t } = useI18n();
  const mutate = useOfflineMutation();
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState("cash");
  const [fromAccount, setFromAccount] = useState("");
  const [reference, setReference] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) reset();
    if (open && bill) setAmount(String(bill.amount_due ?? ""));
    setError("");
    setMethod("cash");
    setFromAccount("");
    setReference("");
  }, [open, bill, reset]);

  async function pay() {
    setError("");
    if (method === "bank_transfer" && !fromAccount) {
      setError(t("sales.chooseBankErr"));
      return;
    }
    setBusy(true);
    try {
      const body = {
        client_uuid: idFor(),
        supplier: bill.supplier,
        bill: bill.id,
        method,
        amount,
      };
      if (method === "bank_transfer") {
        body.from_bank_account = Number(fromAccount);
        if (reference) body.reference_last4 = reference;
      }
      await mutate("supplier_payment", purchasing.createSupplierPayment, body);
      reset();
      onPaid();
      onClose();
    } catch (err) {
      setError(errorText(err, t, "purchasing.saveError"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={t("purchasing.recordPayment")}
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button onClick={pay} disabled={busy || !amount}>
            {busy ? t("purchasing.paying") : t("purchasing.recordPayment")}
          </Button>
        </div>
      }
    >
      {bill && (
        <div className="space-y-4">
          <div className="rounded-card border border-line p-3 text-sm">
            <div className="flex justify-between">
              <span className="text-muted">{t("purchasing.supplier")}</span>
              <span className="text-ink">{supplierName}</span>
            </div>
            <div className="mt-1 flex justify-between">
              <span className="text-muted">{t("purchasing.amountDue")}</span>
              <span className="tabular text-ink">
                {money(bill.amount_due)}
                {bill.currency && <span className="ms-1 text-xs text-muted">{bill.currency}</span>}
              </span>
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
              <Input type="number" value={amount} onChange={(e) => setAmount(e.target.value)} />
            </Field>
          </div>
          {method === "bank_transfer" && (
            <div className="grid grid-cols-2 gap-3">
              <Field label={t("purchasing.fromAccount")}>
                <Select value={fromAccount} onChange={(e) => setFromAccount(e.target.value)}>
                  <option value="">{t("common.select")}</option>
                  {(bankAccounts || []).map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.bank_name}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label={t("sales.refLast4")}>
                <Input
                  value={reference}
                  onChange={(e) => setReference(e.target.value.slice(0, 4))}
                  maxLength={4}
                />
              </Field>
            </div>
          )}
          {error && <p className="text-sm text-danger">{error}</p>}
        </div>
      )}
    </Drawer>
  );
}

export default function BillList({ suppliersById, bankAccounts, writable, refreshKey, onNew }) {
  const { t } = useI18n();
  const { can } = useAuth();
  const canVoid = can("finance.approve");
  const fxInfo = usePurchaseCurrencies();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [payFor, setPayFor] = useState(null);
  const [voiding, setVoiding] = useState(null);
  // Opens on the bills still owing; "all" pages through history. Only the 50
  // newest bills used to load, so an older unpaid one could not be paid.
  const [onlyUnpaid, setOnlyUnpaid] = useState(true);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);

  const load = useCallback((nextPage = 1) => {
    setLoading(true);
    purchasing
      .bills({ page: nextPage, ...(onlyUnpaid ? { unpaid: 1 } : {}) })
      .then((r) => {
        setRows((prev) => (nextPage === 1 ? r.data.results : [...prev, ...r.data.results]));
        setHasMore(Boolean(r.data.next));
        setPage(nextPage);
      })
      .catch(() => { if (nextPage === 1) setRows([]); })
      .finally(() => setLoading(false));
  }, [onlyUnpaid]);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  return (
    <Card>
      <div className="flex items-center justify-end gap-2 border-b border-line px-4 py-2">
        <label className="tap inline-flex items-center gap-2 text-sm text-muted">
          <input type="checkbox" checked={onlyUnpaid} onChange={(e) => setOnlyUnpaid(e.target.checked)} />
          {t("purchasing.onlyUnpaid")}
        </label>
      </div>
      <div className="overflow-x-auto">
        <table className="stack-sm w-full sm:min-w-[640px] text-sm">
          <thead>
            <tr className="border-b border-line text-xs uppercase tracking-wide text-muted">
              <th className="px-4 py-3 text-start font-medium">{t("purchasing.supplier")}</th>
              <th className="px-4 py-3 text-start font-medium">{t("sales.invoice")}</th>
              <th className="px-4 py-3 text-end font-medium">{t("common.total")}</th>
              <th className="px-4 py-3 text-end font-medium">{t("purchasing.amountDue")}</th>
              <th className="px-4 py-3 text-end font-medium">{t("common.status")}</th>
              {writable && <th className="px-4 py-3" />}
            </tr>
          </thead>
          <tbody>
            {loading && (
              <SkeletonTableRows cols={writable ? 6 : 5} />
            )}
            {!loading && rows.length === 0 && (
              <EmptyTableRow
                cols={writable ? 6 : 5}
                icon={FileText}
                title={t("purchasing.emptyBillsTitle")}
                body={t("purchasing.emptyBillsBody")}
                action={writable && onNew && (
                  <Button onClick={onNew}><Plus size={16} /> {t("purchasing.newBill")}</Button>
                )}
              />
            )}
            {!loading &&
              rows.map((b) => (
                <tr key={b.id} className="border-b border-line last:border-0">
                  <td className="px-4 py-3 text-ink">
                    {suppliersById[b.supplier] || `#${b.supplier}`}
                  </td>
                  <td className="px-4 py-3 text-muted">{b.supplier_invoice_number || "—"}</td>
                  <td className="tabular px-4 py-3 text-end text-ink"><BillAmount bill={b} amount={b.total} info={fxInfo} /></td>
                  <td className="tabular px-4 py-3 text-end text-ink"><BillAmount bill={b} amount={b.amount_due} info={fxInfo} /></td>
                  <td className="px-4 py-3 text-end">
                    <Badge tone={statusTone[b.status] || "muted"}>{t(`purchasing.billStatus.${b.status}`)}</Badge>
                  </td>
                  {writable && (
                    <td className="px-4 py-3 text-end">
                      {Number(b.amount_due) > 0 && !b.is_void && (
                        <button
                          onClick={() => setPayFor(b)}
                          className="text-sm text-accent hover:underline"
                        >
                          {t("purchasing.pay")}
                        </button>
                      )}
                      {canVoid && !b.is_void && Number(b.amount_paid) === 0 && (
                        <button
                          onClick={() => setVoiding(b)}
                          className="ms-3 text-sm text-danger hover:underline"
                        >
                          {t("corrections.voidBill")}
                        </button>
                      )}
                    </td>
                  )}
                </tr>
              ))}
          </tbody>
        </table>
      </div>
      {hasMore && (
        <div className="border-t border-line p-3 text-center">
          <Button variant="outline" disabled={loading} onClick={() => load(page + 1)}>{t("purchasing.loadMoreBills")}</Button>
        </div>
      )}
      <PaymentDrawer
        bill={payFor}
        supplierName={payFor ? suppliersById[payFor.supplier] : ""}
        bankAccounts={bankAccounts}
        open={Boolean(payFor)}
        onClose={() => setPayFor(null)}
        onPaid={() => load(1)}
      />
      <VoidDrawer
        open={Boolean(voiding)}
        onClose={() => setVoiding(null)}
        onDone={() => load(1)}
        title={t("corrections.voidBill")}
        summary={voiding ? `${suppliersById[voiding.supplier] || ""} · ${money(voiding.total)}` : ""}
        submit={(body) => purchasing.voidBill(voiding.id, body)}
      />
    </Card>
  );
}
