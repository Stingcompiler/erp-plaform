"use client";

import { useEffect, useState } from "react";
import { Plus, Trash2 } from "lucide-react";

import { purchasing, returns } from "@/lib/api";
import { useI18n } from "../../app/providers/I18nProvider";
import Drawer from "@/components/ui/Drawer";
import { Button, Field, Input, Select } from "@/components/ui/kit";

/**
 * Records goods going back to a supplier.
 *
 * The purchasing side had no creation screen at all — the API and models
 * existed, but nothing could raise a purchase return, so the whole flow was
 * unreachable from the app.
 *
 * Unlike a sales return the goods leave immediately (there is nothing to
 * quarantine). Every row is selected from its original receipt, so the server
 * can enforce the returnable quantity and derive the debit note value.
 */
export default function NewPurchaseReturnDrawer({ open, onClose, onCreated }) {
  const { t } = useI18n();
  const [suppliers, setSuppliers] = useState([]);
  const [warehouses, setWarehouses] = useState([]);
  const [bills, setBills] = useState([]);
  const [receipts, setReceipts] = useState([]);

  const [supplier, setSupplier] = useState("");
  const [receipt, setReceipt] = useState("");
  const [warehouse, setWarehouse] = useState("");
  const [bill, setBill] = useState("");
  const [reason, setReason] = useState("");
  const [debitAmount, setDebitAmount] = useState("");
  const [lines, setLines] = useState([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setSupplier("");
    setReceipt("");
    setWarehouse("");
    setBill("");
    setReason("");
    setDebitAmount("");
    setLines([]);
    setError("");
    purchasing.suppliers({ page: 1 }).then((r) => setSuppliers(r.data.results)).catch(() => {});
    inventory.warehouses().then((r) => setWarehouses(r.data.results)).catch(() => {});
  }, [open]);

  // Only this supplier's bills can be credited against.
  useEffect(() => {
    if (!supplier) {
      setBills([]);
      setReceipts([]);
      return;
    }
    Promise.all([
      purchasing.bills({ page: 1 }),
      purchasing.goodsReceipts({ page: 1, supplier }),
    ]).then(([billResponse, receiptResponse]) => {
      setBills((billResponse.data.results || []).filter((b) => String(b.supplier) === supplier));
      setReceipts(receiptResponse.data.results || receiptResponse.data);
    }).catch(() => {
      setBills([]);
      setReceipts([]);
    });
  }, [supplier]);

  const supplierReceipts = receipts;
  const selectedReceipt = receipts.find((r) => String(r.id) === receipt);

  useEffect(() => {
    setReceipt("");
    setWarehouse("");
    setLines([]);
  }, [supplier]);

  useEffect(() => {
    if (!selectedReceipt) return;
    setWarehouse(String(selectedReceipt.warehouse));
    setLines([]);
  }, [selectedReceipt]);

  const addLine = () => setLines((ls) => [...ls, { goods_receipt_line: "", quantity: "1" }]);
  const setLine = (i, patch) =>
    setLines((ls) => ls.map((l, n) => (n === i ? { ...l, ...patch } : l)));
  const removeLine = (i) => setLines((ls) => ls.filter((_, n) => n !== i));

  async function submit() {
    setError("");
    if (!supplier || !warehouse || !receipt) {
      setError(t("returns.chooseSupplierWarehouse"));
      return;
    }
    const payload = lines.filter((l) => l.goods_receipt_line && Number(l.quantity) > 0);
    if (payload.length === 0) {
      setError(t("returns.addAtLeastOneLine"));
      return;
    }
    setBusy(true);
    try {
      await returns.createPurchaseReturn({
        client_uuid: crypto.randomUUID(),
        supplier: Number(supplier),
        warehouse: Number(warehouse),
        goods_receipt: Number(receipt),
        reason,
        ...(bill ? { bill: Number(bill) } : {}),
        ...(debitAmount ? { debit_amount: String(debitAmount) } : {}),
        lines: payload.map((l) => ({
          goods_receipt_line: Number(l.goods_receipt_line),
          quantity: String(l.quantity),
        })),
      });
      onCreated();
      onClose();
    } catch (err) {
      const data = err?.response?.data;
      setError(
        typeof data === "object" && data
          ? Object.values(data).flat().join(" ")
          : t("returns.saveError"),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={t("returns.newPurchaseReturn")}
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button onClick={submit} disabled={busy}>
            {busy ? t("common.saving") : t("returns.recordReturn")}
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        <p className="rounded-card border border-line bg-paper p-3 text-xs text-muted">
          {t("returns.purchaseReturnHelp")}
        </p>

        <div className="grid grid-cols-2 gap-3">
          <Field label={t("purchasing.supplier")}>
            <Select value={supplier} onChange={(e) => setSupplier(e.target.value)}>
              <option value="">{t("common.select")}</option>
              {suppliers.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={t("returns.originalReceipt")}>
            <Select value={receipt} onChange={(e) => setReceipt(e.target.value)} disabled={!supplier}>
              <option value="">{t("common.select")}</option>
              {supplierReceipts.map((r) => (
                <option key={r.id} value={r.id}>#{r.id}</option>
              ))}
            </Select>
          </Field>
          <Field label={t("returns.fromWarehouse")}>
            <Select value={warehouse} disabled>
              <option value="">{t("common.select")}</option>
              {warehouses.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        <Field label={t("returns.reason")}>
          <Input value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>

        {/* ---- lines ---- */}
        <div>
          <div className="mb-2 flex items-center justify-between">
            <span className="text-sm font-medium text-ink">
              {t("returns.returnedItems")}
            </span>
            <Button variant="outline" onClick={addLine}>
              <Plus size={15} /> {t("common.add")}
            </Button>
          </div>
          {lines.length === 0 && (
            <p className="text-sm text-muted">{t("returns.noLinesYet")}</p>
          )}
          <div className="space-y-2">
            {lines.map((l, i) => (
              <div key={i} className="flex items-end gap-2">
                <div className="min-w-0 flex-1">
                  <Select
                    value={l.goods_receipt_line}
                    onChange={(e) => setLine(i, { goods_receipt_line: e.target.value })}
                  >
                    <option value="">{t("returns.searchProduct")}</option>
                    {(selectedReceipt?.lines || []).filter(
                      (line) => Number(line.returnable_quantity) > 0,
                    ).map((line) => (
                      <option key={line.id} value={line.id}>
                        {line.product_name || `#${line.product}`} · {line.returnable_quantity}
                      </option>
                    ))}
                  </Select>
                </div>
                <div className="w-24">
                  <Input
                    type="number"
                    value={l.quantity}
                    onChange={(e) => setLine(i, { quantity: e.target.value })}
                  />
                </div>
                <button
                  onClick={() => removeLine(i)}
                  aria-label={t("common.delete")}
                  className="rounded-control p-2 text-muted hover:bg-paper hover:text-danger"
                >
                  <Trash2 size={16} />
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* ---- debit note (Rule #6) ---- */}
        <div className="rounded-card border border-line p-3">
          <div className="mb-2 text-sm font-medium text-ink">
            {t("doc.titleDebitNote")}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label={t("doc.amount")} hint={t("returns.debitAmountHint")}>
              <Input
                type="number"
                value={debitAmount}
                onChange={(e) => setDebitAmount(e.target.value)}
              />
            </Field>
            <Field label={t("purchasing.bills")}>
              <Select
                value={bill}
                onChange={(e) => setBill(e.target.value)}
                disabled={!supplier}
              >
                <option value="">{t("returns.noBillLink")}</option>
                {bills.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.supplier_invoice_number || `#${b.id}`}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
        </div>

        {error && <p className="text-sm text-danger">{error}</p>}
      </div>
    </Drawer>
  );
}
