"use client";

import { useEffect, useState } from "react";
import { Search, Trash2 } from "lucide-react";

import { inventory, returns, sales } from "@/lib/api";
import { useI18n } from "../../app/providers/I18nProvider";
import { useToast } from "@/components/ui/Toast";
import Drawer from "@/components/ui/Drawer";
import BarcodeScanInput from "@/components/inventory/BarcodeScanInput";
import { Button, Field, Input, Select } from "@/components/ui/kit";

export default function NewReturnDrawer({ open, onClose, onCreated }) {
  const { t } = useI18n();
  const toast = useToast();
  const [invoices, setInvoices] = useState([]);
  const [invoice, setInvoice] = useState("");
  const [reason, setReason] = useState("");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [lines, setLines] = useState([]);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setInvoice("");
      setReason("");
      setLines([]);
      setError("");
      sales.invoices({ page: 1 }).then((r) => setInvoices(r.data.results)).catch(() => {});
    }
  }, [open]);

  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      return undefined;
    }
    const timer = setTimeout(() => {
      inventory
        .products({ search: query })
        .then((r) => setResults(r.data.results.slice(0, 6)))
        .catch(() => setResults([]));
    }, 250);
    return () => clearTimeout(timer);
  }, [query]);

  function addProduct(p) {
    setLines((ls) =>
      ls.find((l) => l.id === p.id)
        ? ls
        : [...ls, { id: p.id, sku: p.sku, name: p.name, qty: "1" }]
    );
    setQuery("");
    setResults([]);
  }

  // Scanned returns: the product must belong to the selected invoice (Rule #4 —
  // a return line references the original document). Scanning something that was
  // never on this invoice is rejected rather than silently added.
  function onScan(product) {
    if (!invoice) {
      toast.error(t("returns.scanFirstInvoice"));
      return;
    }
    const inv = invoices.find((i) => String(i.id) === String(invoice));
    const onInvoice = (inv?.lines || []).some((l) => l.product === product.id);
    if (!onInvoice) {
      toast.error(t("returns.scanNotOnInvoice", { name: product.name }));
      return;
    }
    addProduct(product);
  }

  const updateQty = (id, qty) =>
    setLines((ls) => ls.map((l) => (l.id === id ? { ...l, qty } : l)));
  const removeLine = (id) => setLines((ls) => ls.filter((l) => l.id !== id));

  async function save() {
    setError("");
    if (!invoice) return setError(t("returns.chooseInvoiceErr"));
    if (lines.length === 0) return setError(t("returns.addProductErr"));
    setSaving(true);
    try {
      await returns.createSalesReturn({
        client_uuid: crypto.randomUUID(),
        invoice: Number(invoice),
        reason,
        lines: lines.map((l) => ({ product: l.id, quantity: String(l.qty) })),
      });
      onCreated();
      onClose();
    } catch (err) {
      const data = err?.response?.data;
      setError(
        typeof data === "object" && data
          ? Object.values(data).flat().join(" ")
          : t("returns.createError")
      );
    } finally {
      setSaving(false);
    }
  }

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
          <Button onClick={save} disabled={saving || !invoice || lines.length === 0}>
            {saving ? t("returns.creating") : t("returns.createReturn")}
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        <Field label={t("returns.invoice")}>
          <Select value={invoice} onChange={(e) => setInvoice(e.target.value)}>
            <option value="">{t("returns.selectInvoice")}</option>
            {invoices.map((inv) => (
              <option key={inv.id} value={inv.id}>
                {(inv.number_display || inv.number) + " · " + (inv.customer_name || t("sales.walkIn"))}
              </option>
            ))}
          </Select>
        </Field>

        <Field label={t("returns.reason")}>
          <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder={t("common.optional")} />
        </Field>

        <div>
          <span className="mb-1 block text-sm font-medium text-ink">{t("returns.returnedItems")}</span>
          {/* Scan to add — only once an invoice is chosen, since the scan is
              validated against that invoice's lines. */}
          {invoice && (
            <div className="mb-2">
              <BarcodeScanInput onScan={onScan} autoFocus={false} />
            </div>
          )}
          <div className="relative">
            <Search size={16} className="pointer-events-none absolute inset-y-0 start-3 my-auto text-muted" />
            <Input
              placeholder={t("returns.searchProduct")}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="ps-9"
            />
            {results.length > 0 && (
              <div className="absolute z-10 mt-1 w-full overflow-hidden rounded-card border border-line bg-surface shadow-card">
                {results.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => addProduct(p)}
                    className="flex w-full items-center justify-between px-3 py-2 text-start text-sm hover:bg-paper"
                  >
                    <span className="text-ink">{p.name}</span>
                    <span className="tabular text-muted">{p.sku}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="mt-3 space-y-2">
            {lines.map((l) => (
              <div key={l.id} className="flex items-center gap-3 rounded-card border border-line px-3 py-2">
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm text-ink">{l.name}</div>
                  <div className="tabular text-xs text-muted">{l.sku}</div>
                </div>
                <Input
                  type="number"
                  value={l.qty}
                  onChange={(e) => updateQty(l.id, e.target.value)}
                  className="w-20"
                />
                <button onClick={() => removeLine(l.id)} className="text-muted hover:text-danger">
                  <Trash2 size={15} />
                </button>
              </div>
            ))}
          </div>
        </div>

        {error && <p className="text-sm text-danger">{error}</p>}
        <p className="text-xs text-muted">{t("returns.quarantineNote")}</p>
      </div>
    </Drawer>
  );
}
