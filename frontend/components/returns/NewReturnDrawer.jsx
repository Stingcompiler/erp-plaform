"use client";

import { useEffect, useMemo, useState } from "react";

import { returns, sales } from "@/lib/api";
import { useI18n } from "../../app/providers/I18nProvider";
import { useOfflineMutation } from "@/components/sync/useOfflineMutation";
import { useToast } from "@/components/ui/Toast";
import Drawer from "@/components/ui/Drawer";
import BarcodeScanInput from "@/components/inventory/BarcodeScanInput";
import { Button, Field, Input, Select } from "@/components/ui/kit";
import { errorText } from "@/lib/errors";

// Rule #4: a return is a child of the original invoice, so the form is driven
// by that invoice's own lines rather than a free product search. This is what
// lets every line carry its `invoice_line` id — without it the server cannot
// price the credit note, and returns land uncredited.
export default function NewReturnDrawer({ open, onClose, onCreated }) {
  const { t } = useI18n();
  const mutate = useOfflineMutation();
  const toast = useToast();
  const [invoices, setInvoices] = useState([]);
  const [invoiceId, setInvoiceId] = useState("");
  const [reason, setReason] = useState("");
  // { [invoiceLineId]: "qty as typed" }
  const [qty, setQty] = useState({});
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setInvoiceId("");
    setReason("");
    setQty({});
    setError("");
    sales
      .invoices({ page: 1 })
      .then((r) => setInvoices(r.data.results))
      .catch(() => {});
  }, [open]);

  const invoice = useMemo(
    () => invoices.find((i) => String(i.id) === String(invoiceId)) || null,
    [invoices, invoiceId]
  );

  // The server is the authority on what's still returnable; it sends the
  // remainder per line so the field can cap itself instead of submitting a
  // number that will bounce.
  const returnableOf = (line) =>
    Number(line.returnable_quantity ?? line.quantity ?? 0);

  function setLineQty(lineId, value, max) {
    if (value === "") {
      setQty((q) => ({ ...q, [lineId]: "" }));
      return;
    }
    const n = Number(value);
    if (Number.isNaN(n) || n < 0) return;
    setQty((q) => ({ ...q, [lineId]: String(Math.min(n, max)) }));
  }

  // Scanning bumps the matching invoice line by one, capped at its remainder.
  function onScan(product) {
    if (!invoice) {
      toast.error(t("returns.scanFirstInvoice"));
      return;
    }
    const line = (invoice.lines || []).find((l) => l.product === product.id);
    if (!line) {
      toast.error(t("returns.scanNotOnInvoice", { name: product.name }));
      return;
    }
    const max = returnableOf(line);
    if (max <= 0) {
      toast.error(t("returns.lineFullyReturned", { name: product.name }));
      return;
    }
    const next = Number(qty[line.id] || 0) + 1;
    if (next > max) {
      toast.error(t("returns.scanExceedsRemaining", { name: product.name }));
      return;
    }
    setQty((q) => ({ ...q, [line.id]: String(next) }));
  }

  const payloadLines = useMemo(() => {
    if (!invoice) return [];
    return (invoice.lines || [])
      .filter((l) => Number(qty[l.id] || 0) > 0)
      .map((l) => ({
        invoice_line: l.id,
        product: l.product,
        quantity: String(qty[l.id]),
      }));
  }, [invoice, qty]);

  async function save() {
    setError("");
    if (!invoice) return setError(t("returns.chooseInvoiceErr"));
    if (payloadLines.length === 0) return setError(t("returns.addProductErr"));
    setSaving(true);
    try {
      await mutate("sales_return", returns.createSalesReturn, {
        client_uuid: crypto.randomUUID(),
        invoice: invoice.id,
        reason,
        lines: payloadLines,
      });
      onCreated();
      onClose();
    } catch (err) {
      setError(errorText(err, t, "returns.createError"));
    } finally {
      setSaving(false);
    }
  }

  const lines = invoice?.lines || [];
  const nothingReturnable =
    invoice && lines.every((l) => returnableOf(l) <= 0);

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={t("returns.newSalesReturn")}
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button
            onClick={save}
            disabled={saving || !invoice || payloadLines.length === 0}
          >
            {saving ? t("returns.creating") : t("returns.createReturn")}
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        <Field label={t("returns.invoice")}>
          <Select
            value={invoiceId}
            onChange={(e) => {
              setInvoiceId(e.target.value);
              setQty({});
            }}
          >
            <option value="">{t("returns.selectInvoice")}</option>
            {invoices.map((inv) => (
              <option key={inv.id} value={inv.id}>
                {(inv.number_display || inv.number) +
                  " · " +
                  (inv.customer_name || t("sales.walkIn"))}
              </option>
            ))}
          </Select>
        </Field>

        <Field label={t("returns.reason")}>
          <Input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder={t("common.optional")}
          />
        </Field>

        <div>
          <span className="mb-1 block text-sm font-medium text-ink">
            {t("returns.returnedItems")}
          </span>

          {!invoice && (
            <p className="text-sm text-muted">{t("returns.pickInvoiceFirst")}</p>
          )}

          {invoice && (
            <>
              <div className="mb-2">
                <BarcodeScanInput onScan={onScan} autoFocus={false} />
              </div>

              {nothingReturnable && (
                <p className="text-sm text-muted">
                  {t("returns.everythingReturned")}
                </p>
              )}

              <div className="space-y-2">
                {lines.map((l) => {
                  const max = returnableOf(l);
                  const spent = max <= 0;
                  return (
                    <div
                      key={l.id}
                      className={
                        "flex items-center gap-3 rounded-card border border-line px-3 py-2 " +
                        (spent ? "opacity-50" : "")
                      }
                    >
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm text-ink">
                          {l.product_name || l.description}
                        </div>
                        <div className="tabular text-xs text-muted">
                          {l.product_sku}
                          {" · "}
                          {spent
                            ? t("returns.fullyReturned")
                            : t("returns.returnableOf", {
                                remaining: max,
                                sold: Number(l.quantity),
                              })}
                        </div>
                      </div>
                      {/* Input is w-full by design; size it through a wrapper
                          so the label column keeps its room. */}
                      <div className="w-20 shrink-0">
                        <Input
                          type="number"
                          inputMode="decimal"
                          min="0"
                          max={String(max)}
                          step="any"
                          disabled={spent}
                          placeholder="0"
                          value={qty[l.id] ?? ""}
                          onChange={(e) => setLineQty(l.id, e.target.value, max)}
                          aria-label={`${t("returns.quantity")} ${l.product_sku || ""}`}
                          className="text-end"
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </div>

        {error && <p className="text-sm text-danger">{error}</p>}
        <p className="text-xs text-muted">{t("returns.quarantineNote")}</p>
      </div>
    </Drawer>
  );
}
