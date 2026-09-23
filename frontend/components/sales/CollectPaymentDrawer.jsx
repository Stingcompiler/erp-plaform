"use client";

import { useEffect, useMemo, useState } from "react";
import { Printer } from "lucide-react";

import { bankAccounts as bankAccountsApi, sales } from "@/lib/api";
import { accountLabel } from "@/lib/bankChannels";
import { useI18n } from "../../app/providers/I18nProvider";
import { useOfflineMutation } from "@/components/sync/useOfflineMutation";
import DocumentDrawer from "@/components/print/DocumentDrawer";
import Drawer from "@/components/ui/Drawer";
import { Badge, Button, Field, Input, Select } from "@/components/ui/kit";
import { errorText } from "@/lib/errors";
import { SkeletonLines } from "@/components/ui/Skeleton";

const money = (v) =>
  Number(v ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const round2 = (n) => Math.round((Number(n) || 0) * 100) / 100;

/**
 * Settle a customer's debt. Opened from the debt ledger (whole account) or
 * from an invoice (one invoice). The cashier types what the customer handed
 * over; the amount is allocated across open invoices oldest-first, and each
 * allocation becomes one Payment (the API is per-invoice by design, so the
 * ledger keeps invoice-level truth). Every allocation can be overridden.
 *
 * Works offline: each payment goes through the sync queue as a "payment"
 * op, which the server already accepts. Bank transfers carry the receiving
 * account, sender bank and reference the API requires.
 */
export default function CollectPaymentDrawer({ open, onClose, customer, invoice, onDone }) {
  const { t, language } = useI18n();
  const mutate = useOfflineMutation();
  const [invoices, setInvoices] = useState([]);
  const [loading, setLoading] = useState(false);
  const [accounts, setAccounts] = useState([]);
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState("cash");
  const [account, setAccount] = useState("");
  const [senderBank, setSenderBank] = useState("");
  const [reference, setReference] = useState("");
  const [overrides, setOverrides] = useState({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [receiptId, setReceiptId] = useState(null);
  const [credit, setCredit] = useState(null);
  const [creditNote, setCreditNote] = useState("");

  useEffect(() => {
    if (!open) return;
    setAmount(""); setMethod("cash"); setAccount(""); setSenderBank(""); setReference("");
    setOverrides({}); setError(""); setResult(null);
    bankAccountsApi.list().then((r) => setAccounts(r.data.results ?? r.data)).catch(() => setAccounts([]));
    setCredit(null); setCreditNote("");
    const customerId = customer?.id ?? invoice?.customer;
    if (customerId) {
      sales.customerCredit(customerId)
        .then((r) => { if (Number(r.data.total) > 0) { setCredit(r.data); setCreditNote(String(r.data.notes[0].id)); } })
        .catch(() => {});
    }
    if (invoice) {
      setInvoices([invoice]);
      setAmount(String(invoice.amount_due ?? ""));
      return;
    }
    if (!customer) return;
    setLoading(true);
    sales.invoices({ customer: customer.id, open: 1, page_size: 200 })
      .then((r) => setInvoices(r.data.results ?? r.data))
      .catch(() => setError(t("debts.collectLoadError")))
      .finally(() => setLoading(false));
  }, [open, customer, invoice, t]);

  const totalDue = useMemo(
    () => round2(invoices.reduce((sum, inv) => sum + Number(inv.amount_due || 0), 0)),
    [invoices],
  );

  // Oldest-first allocation of the typed amount; a manual override on any
  // invoice is honoured and the remainder flows on to the next ones.
  const allocation = useMemo(() => {
    let left = round2(amount);
    const rows = [];
    for (const inv of invoices) {
      const due = round2(inv.amount_due);
      const forced = overrides[inv.id];
      let take;
      if (forced !== undefined && forced !== "") {
        take = Math.min(round2(forced), due);
      } else {
        take = Math.max(0, Math.min(due, left));
      }
      take = round2(take);
      left = round2(left - take);
      rows.push({ invoice: inv, take });
    }
    return { rows, unallocated: Math.max(0, left) };
  }, [amount, invoices, overrides]);

  const allocatedTotal = round2(allocation.rows.reduce((s, r) => s + r.take, 0));
  const overAllocated = allocatedTotal > round2(amount) + 0.001;

  async function collect() {
    setError("");
    if (!(round2(amount) > 0)) return setError(t("debts.amountRequired"));
    if (allocatedTotal <= 0) return setError(t("debts.nothingToAllocate"));
    if (overAllocated) return setError(t("debts.overAllocated"));
    if (method === "bank_transfer") {
      if (!account) return setError(t("sales.chooseBankErr"));
      if (!senderBank.trim()) return setError(t("debts.senderBankRequired"));
      if (!reference.trim()) return setError(t("debts.referenceRequired"));
    }
    if (method === "credit") {
      const note = credit?.notes.find((n) => String(n.id) === creditNote);
      if (!note) return setError(t("debts.creditRequired"));
      if (round2(amount) > Number(note.remaining) + 0.001) return setError(t("debts.creditExceeded", { remaining: money(note.remaining) }));
    }
    setBusy(true);
    const done = [];
    let queued = 0;
    // One collection = one receipt: every invoice's payment carries the same
    // group so a single transfer reference may settle several invoices
    // without tripping the duplicate-reference guard.
    const receiptGroup = crypto.randomUUID();
    try {
      for (const row of allocation.rows) {
        if (row.take <= 0) continue;
        const body = {
          client_uuid: crypto.randomUUID(),
          invoice: row.invoice.id,
          method,
          amount: row.take.toFixed(2),
          receipt_group: receiptGroup,
        };
        if (method === "bank_transfer") {
          body.company_bank_account = Number(account);
          body.sender_bank_name = senderBank.trim();
          body.transfer_reference = reference.trim();
        }
        if (method === "credit") body.credit_note = Number(creditNote);
        const res = await mutate("payment", (payload) => sales.createPayment(payload), body);
        if (res.queued) queued += 1;
        else done.push(res.data);
      }
      setResult({ count: done.length + queued, queued, payments: done, total: allocatedTotal });
      onDone?.();
    } catch (err) {
      setError(errorText(err, t, "debts.collectError"));
      if (done.length) onDone?.();
    } finally {
      setBusy(false);
    }
  }

  const title = invoice
    ? t("debts.collectForInvoice", { number: invoice.number_display })
    : t("debts.collectTitle");

  return (
    <>
    <DocumentDrawer
      id={receiptId}
      open={Boolean(receiptId)}
      onClose={() => setReceiptId(null)}
      fetcher={sales.paymentDocument}
      title={t("debts.receipt")}
    />
    <Drawer
      open={open}
      onClose={onClose}
      title={title}
      protectChanges={!result}
      footer={
        result ? (
          <div className="flex justify-end"><Button onClick={onClose}>{t("common.close")}</Button></div>
        ) : (
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={onClose}>{t("common.cancel")}</Button>
            <Button onClick={collect} disabled={busy || loading || !(round2(amount) > 0)}>
              {busy ? t("debts.collecting") : t("debts.collectAction", { amount: money(allocatedTotal) })}
            </Button>
          </div>
        )
      }
    >
      {result ? (
        <div className="space-y-4">
          <div className="rounded-card border border-ok/30 bg-ok/5 p-4 text-sm">
            <div className="font-semibold text-ink">{t("debts.collected", { amount: money(result.total) })}</div>
            <p className="mt-1 text-muted">
              {result.queued
                ? t("debts.collectedQueued", { count: result.queued })
                : t("debts.collectedCount", { count: result.count })}
            </p>
          </div>
          {result.payments.length > 0 && (
            <div className="divide-y divide-line rounded-card border border-line">
              {result.payments.map((p) => (
                <div key={p.id} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
                  <span className="tabular">#{p.id} · {money(p.amount)}</span>
                  <Button variant="ghost" onClick={() => setReceiptId(p.id)}>
                    <Printer size={14} />{t("debts.printReceipt")}
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-4">
          <div className="rounded-card border border-line p-3 text-sm">
            <div className="flex justify-between">
              <span className="text-muted">{t("debts.customerLabel")}</span>
              <span className="font-medium text-ink">{customer?.name || invoice?.customer_name || "—"}</span>
            </div>
            <div className="mt-1 flex justify-between">
              <span className="text-muted">{t("debts.totalDue")}</span>
              <span className="tabular font-semibold text-ink">{money(totalDue)}</span>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Field label={t("common.amount")}>
              <Input
                type="number" inputMode="decimal" min="0" step="0.01" autoFocus
                value={amount}
                onChange={(e) => { setAmount(e.target.value); setOverrides({}); }}
                placeholder={money(totalDue)}
              />
            </Field>
            <Field label={t("common.method")}>
              <Select value={method} onChange={(e) => setMethod(e.target.value)}>
                <option value="cash">{t("common.cash")}</option>
                <option value="bank_transfer">{t("common.bankTransfer")}</option>
                {credit && <option value="credit">{t("debts.storeCredit", { amount: money(credit.total) })}</option>}
              </Select>
            </Field>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={() => { setAmount(String(totalDue)); setOverrides({}); }}>
              {t("debts.payAll")}
            </Button>
            {credit && method !== "credit" && (
              <Button variant="ghost" onClick={() => { setMethod("credit"); setAmount(String(Math.min(Number(credit.total), totalDue))); setOverrides({}); }}>
                {t("debts.useCredit", { amount: money(Math.min(Number(credit.total), totalDue)) })}
              </Button>
            )}
          </div>
          {method === "credit" && credit && (
            <Field label={t("debts.creditNoteLabel")}>
              <Select value={creditNote} onChange={(e) => setCreditNote(e.target.value)}>
                {credit.notes.map((n) => <option key={n.id} value={n.id}>{n.number} · {money(n.remaining)}{n.invoice ? ` · ${n.invoice}` : ""}</option>)}
              </Select>
            </Field>
          )}

          {method === "bank_transfer" && (
            <div className="grid gap-3 sm:grid-cols-3">
              <Field label={t("sales.receivingAccount")}>
                <Select value={account} onChange={(e) => setAccount(e.target.value)}>
                  <option value="">{t("common.select")}</option>
                  {accounts.map((a) => (
                    <option key={a.id} value={a.id}>{accountLabel(t, a)}</option>
                  ))}
                </Select>
              </Field>
              <Field label={t("sales.senderName")}>
                <Input value={senderBank} onChange={(e) => setSenderBank(e.target.value)} />
              </Field>
              <Field label={t("sales.transferReference")}>
                <Input value={reference} maxLength={64} dir="ltr"
                  onChange={(e) => setReference(e.target.value.slice(0, 64))} />
              </Field>
            </div>
          )}

          <div>
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-sm font-semibold">{t("debts.allocation")}</h3>
              <span className="text-xs text-muted">{t("debts.allocationHint")}</span>
            </div>
            {loading ? (
              <SkeletonLines />
            ) : invoices.length === 0 ? (
              <p className="py-4 text-center text-sm text-muted">{t("debts.noOpenInvoices")}</p>
            ) : (
              <div className="divide-y divide-line rounded-card border border-line">
                {allocation.rows.map(({ invoice: inv, take }) => (
                  <div key={inv.id} className="flex items-center gap-3 px-3 py-2 text-sm">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium" dir="ltr">{inv.number_display}</span>
                        {inv.is_overdue && <Badge tone="danger">{t("debts.overdue")}</Badge>}
                      </div>
                      <div className="text-xs text-muted">
                        {new Date(inv.issued_at).toLocaleDateString(language === "ar" ? "ar" : "en")}
                        {" · "}{t("debts.dueOf", { due: money(inv.amount_due), total: money(inv.total) })}
                      </div>
                    </div>
                    <div className="w-28 shrink-0">
                      <Input
                        type="number" inputMode="decimal" min="0" max={inv.amount_due} step="0.01"
                        className="text-end"
                        value={overrides[inv.id] ?? (take ? take.toFixed(2) : "")}
                        placeholder="0.00"
                        aria-label={`${t("common.amount")} ${inv.number_display}`}
                        onChange={(e) => setOverrides((o) => ({ ...o, [inv.id]: e.target.value }))}
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}
            <div className="mt-2 flex justify-between text-xs text-muted">
              <span>{t("debts.allocated", { amount: money(allocatedTotal) })}</span>
              {allocation.unallocated > 0 && (
                <span className="text-warn">{t("debts.unallocated", { amount: money(allocation.unallocated) })}</span>
              )}
              {overAllocated && <span className="text-danger">{t("debts.overAllocated")}</span>}
            </div>
          </div>

          {error && <p role="alert" className="text-sm text-danger">{error}</p>}
        </div>
      )}
    </Drawer>
    </>
  );
}
