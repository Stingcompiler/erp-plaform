"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Search, Trash2 } from "lucide-react";

import { inventory, purchasing } from "@/lib/api";
import { useI18n } from "../../app/providers/I18nProvider";
import { useToast } from "@/components/ui/Toast";
import { Badge, Button, Card, Field, Input, Select } from "@/components/ui/kit";
import BarcodeScanInput from "@/components/inventory/BarcodeScanInput";
import { cacheProducts } from "@/lib/productCache";

const money = (v) =>
  Number(v ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export default function ReceivingTerminal({ suppliers, warehouses, onReceived }) {
  const { t } = useI18n();
  const [supplier, setSupplier] = useState("");
  const [warehouse, setWarehouse] = useState("");
  const [note, setNote] = useState("");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [lines, setLines] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");
  const receiptUuid = useRef(null);
  const toast = useToast();

  useEffect(() => {
    if (warehouses.length && !warehouse) setWarehouse(String(warehouses[0].id));
  }, [warehouses, warehouse]);

  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      return undefined;
    }
    const timer = setTimeout(() => {
      inventory
        .products({ search: query })
        .then((r) => {
          setResults(r.data.results.slice(0, 6));
          cacheProducts(r.data.results);
        })
        .catch(() => setResults([]));
    }, 250);
    return () => clearTimeout(timer);
  }, [query]);

  function addProduct(p) {
    if (!receiptUuid.current) receiptUuid.current = crypto.randomUUID();
    setLines((ls) => {
      const found = ls.find((l) => l.id === p.id);
      if (found) return ls.map((l) => (l.id === p.id ? { ...l, qty: l.qty + 1 } : l));
      return [
        ...ls,
        { id: p.id, sku: p.sku, name: p.name, qty: 1, unit_cost: String(p.cost_price ?? "0") },
      ];
    });
    setQuery("");
    setResults([]);
  }

  const updateLine = (id, patch) =>
    setLines((ls) => ls.map((l) => (l.id === id ? { ...l, ...patch } : l)));
  const removeLine = (id) => setLines((ls) => ls.filter((l) => l.id !== id));

  const total = lines.reduce((s, l) => s + Number(l.unit_cost || 0) * Number(l.qty || 0), 0);

  function reset() {
    setLines([]);
    setNote("");
    receiptUuid.current = null;
  }

  async function submit() {
    setError("");
    if (!supplier) return setError(t("purchasing.selectSupplierErr"));
    if (!warehouse) return setError(t("purchasing.selectWarehouseErr"));
    if (lines.length === 0) return setError(t("purchasing.addProductErr"));
    if (!receiptUuid.current) receiptUuid.current = crypto.randomUUID();

    setSubmitting(true);
    try {
      await purchasing.receive({
        client_uuid: receiptUuid.current,
        supplier: Number(supplier),
        warehouse: Number(warehouse),
        note,
        lines: lines.map((l) => ({
          product: l.id,
          quantity: String(l.qty),
          unit_cost: l.unit_cost === "" ? undefined : l.unit_cost,
        })),
      });
      reset();
      setDone(true);
      onReceived?.();
      toast.success(t("purchasing.received"));
    } catch (err) {
      const data = err?.response?.data;
      const msg =
        typeof data === "object" && data
          ? Object.values(data).flat().join(" ")
          : t("purchasing.receivingFailed");
      setError(msg);
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  }

  if (done) {
    return (
      <Card className="mx-auto max-w-md p-6 text-center">
        <div className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-ok/10 text-ok">
          <Check />
        </div>
        <h2 className="mt-3 font-display text-xl font-semibold">{t("purchasing.receivedTitle")}</h2>
        <p className="mt-1 text-muted">{t("purchasing.purchaseInPosted")}</p>
        <Button className="mt-6 w-full" onClick={() => setDone(false)}>
          {t("purchasing.receiveMore")}
        </Button>
      </Card>
    );
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
      <div>
        {/* Scan incoming goods to build the receipt without manual entry. */}
        <div className="mb-3">
          <BarcodeScanInput onScan={addProduct} />
        </div>
        <div className="relative">
          <Search size={16} className="pointer-events-none absolute inset-y-0 start-3 my-auto text-muted" />
          <Input
            placeholder={t("purchasing.searchToReceive")}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="ps-9"
          />
          {results.length > 0 && (
            <Card className="absolute z-10 mt-1 w-full overflow-hidden">
              {results.map((p) => (
                <button
                  key={p.id}
                  onClick={() => addProduct(p)}
                  className="flex w-full items-center justify-between px-4 py-2.5 text-start text-sm hover:bg-paper"
                >
                  <span>
                    <span className="tabular text-muted">{p.sku}</span>{" "}
                    <span className="text-ink">{p.name}</span>
                  </span>
                  <span className="tabular text-muted">{t("purchasing.cost")} {money(p.cost_price)}</span>
                </button>
              ))}
            </Card>
          )}
        </div>

        <Card className="mt-4">
          {lines.length === 0 ? (
            <div className="px-4 py-12 text-center text-muted">
              {t("purchasing.addToReceipt")}
            </div>
          ) : (
            <div className="divide-y divide-line">
              {lines.map((l) => (
                <div key={l.id} className="flex items-center gap-3 px-4 py-3">
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm text-ink">{l.name}</div>
                    <div className="tabular text-xs text-muted">{l.sku}</div>
                  </div>
                  <label className="text-xs text-muted">
                    {t("purchasing.qty")}
                    <Input
                      type="number"
                      value={l.qty}
                      onChange={(e) => updateLine(l.id, { qty: e.target.value })}
                      className="mt-0.5 w-20"
                    />
                  </label>
                  <label className="text-xs text-muted">
                    {t("purchasing.unitCost")}
                    <Input
                      type="number"
                      value={l.unit_cost}
                      onChange={(e) => updateLine(l.id, { unit_cost: e.target.value })}
                      className="mt-0.5 w-24"
                    />
                  </label>
                  <div className="tabular w-24 text-end text-sm text-ink">
                    {money(Number(l.unit_cost || 0) * Number(l.qty || 0))}
                  </div>
                  <button
                    onClick={() => removeLine(l.id)}
                    className="text-muted hover:text-danger"
                    aria-label={t("purchasing.remove")}
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <Card className="h-fit p-5">
        <div className="space-y-4">
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
          <Field label={t("sales.warehouse")}>
            <Select value={warehouse} onChange={(e) => setWarehouse(e.target.value)}>
              {warehouses.length === 0 && <option value="">{t("sales.noWarehouses")}</option>}
              {warehouses.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={t("purchasing.note")}>
            <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder={t("common.optional")} />
          </Field>

          <div className="flex items-center justify-between border-t border-line pt-4">
            <span className="text-sm text-muted">{t("purchasing.goodsValue")}</span>
            <span className="tabular text-lg font-medium text-ink">{money(total)}</span>
          </div>

          {error && <p className="text-sm text-danger">{error}</p>}

          <Button className="w-full" onClick={submit} disabled={submitting || lines.length === 0}>
            {submitting ? t("sales.recording") : t("purchasing.receiveStock")}
          </Button>
          <div className="text-center">
            <Badge tone="muted">{t("purchasing.postsPurchaseIn")}</Badge>
          </div>
        </div>
      </Card>
    </div>
  );
}
