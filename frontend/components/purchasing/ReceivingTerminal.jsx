"use client";

import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Check, Search, Trash2 } from "lucide-react";

import { inventory, purchasing } from "@/lib/api";
import { useI18n } from "../../app/providers/I18nProvider";
import { useOfflineMutation } from "@/components/sync/useOfflineMutation";
import { useToast } from "@/components/ui/Toast";
import { Badge, Button, Card, Field, Input, Select } from "@/components/ui/kit";
import BarcodeScanInput from "@/components/inventory/BarcodeScanInput";
import { cacheProducts } from "@/lib/productCache";
import { errorText } from "@/lib/errors";
import { round2 } from "@/lib/money";
import {
  AmountWithBase, CurrencyFields, EMPTY_FX, fxCurrency, fxPayload, fxProblem, fxRate,
  toDocumentCost, usePurchaseCurrencies,
} from "@/components/purchasing/PurchaseCurrency";

const money = (v) =>
  Number(v ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export default function ReceivingTerminal({ suppliers, warehouses, onReceived, initialOrder = null }) {
  const { t } = useI18n();
  const mutate = useOfflineMutation();
  const [supplier, setSupplier] = useState("");
  const [warehouse, setWarehouse] = useState("");
  const [note, setNote] = useState("");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [lines, setLines] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");
  const [orderId, setOrderId] = useState(null);
  // Supplier currency: picked here for a receipt without an order; an
  // order's receipt is in the order's currency at the order's rate.
  const fxInfo = usePurchaseCurrencies();
  const [fx, setFx] = useState(EMPTY_FX);
  const [orderFx, setOrderFx] = useState(null);

  // "Receive against this order": supplier and the still-outstanding
  // quantities come from the order, at the order's costs; the receipt
  // carries purchase_order so the server caps it at what remains.
  useEffect(() => {
    if (!initialOrder) return;
    setOrderId(initialOrder.id);
    setOrderFx({ currency: initialOrder.currency || "", rate: initialOrder.exchange_rate });
    setSupplier(String(initialOrder.supplier));
    setLines(initialOrder.lines
      .filter((l) => Number(l.remaining_quantity) > 0)
      .map((l) => ({
        id: l.product, sku: l.product_sku, name: l.product_name,
        qty: Number(l.remaining_quantity), unit_cost: String(l.unit_cost ?? "0"),
        tracked: Boolean(l.product_track_batches), lot: "", expiry: "",
      })));
    if (!receiptUuid.current) receiptUuid.current = crypto.randomUUID();
  }, [initialOrder]);
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
        {
          id: p.id, sku: p.sku, name: p.name, qty: 1,
          // Catalogue cost is in the company currency; a USD receipt starts
          // from its USD equivalent at the rate on the form.
          unit_cost: orderId ? String(p.cost_price ?? "0") : toDocumentCost(p.cost_price, fx, fxInfo),
          // Lot and expiry are asked for only on batch-tracked products —
          // the server refuses a tracked line without a lot.
          tracked: Boolean(p.track_batches), lot: "", expiry: "",
        },
      ];
    });
    setQuery("");
    setResults([]);
  }

  const updateLine = (id, patch) =>
    setLines((ls) => ls.map((l) => (l.id === id ? { ...l, ...patch } : l)));
  const removeLine = (id) => setLines((ls) => ls.filter((l) => l.id !== id));

  const total = round2(
    lines.reduce((s, l) => s + round2(Number(l.unit_cost || 0) * Number(l.qty || 0)), 0)
  );
  const currency = orderFx ? orderFx.currency || fxInfo.currency : fxCurrency(fx, fxInfo);
  const rate = orderFx ? Number(orderFx.rate) || 1 : fxRate(fx, fxInfo);

  // "past" | "soon" | null — the shelf-life read the receiver sees while typing.
  const expiryState = (l) => {
    if (!l.expiry) return null;
    const days = Math.round((new Date(`${l.expiry}T00:00:00`) - new Date().setHours(0, 0, 0, 0)) / 86400000);
    if (days < 0) return "past";
    if (days <= 30) return "soon";
    return null;
  };

  function reset() {
    setLines([]);
    setNote("");
    setOrderId(null);
    setOrderFx(null);
    setFx(EMPTY_FX);
    receiptUuid.current = null;
  }

  async function submit() {
    setError("");
    if (!supplier) return setError(t("purchasing.selectSupplierErr"));
    if (!warehouse) return setError(t("purchasing.selectWarehouseErr"));
    if (lines.length === 0) return setError(t("purchasing.addProductErr"));
    const missingLot = lines.find((l) => l.tracked && !l.lot.trim());
    if (missingLot) return setError(t("purchasing.lotRequired", { sku: missingLot.sku }));
    const past = lines.find((l) => expiryState(l) === "past");
    if (past) return setError(t("purchasing.expiryPast", { sku: past.sku }));
    const fxError = orderId ? "" : fxProblem(fx, fxInfo, t);
    if (fxError) return setError(fxError);
    if (!receiptUuid.current) receiptUuid.current = crypto.randomUUID();

    setSubmitting(true);
    try {
      const result = await mutate("goods_receipt", purchasing.receive, {
        client_uuid: receiptUuid.current,
        // When the goods arrived; a queued receipt is dated by it.
        occurred_at: new Date().toISOString(),
        supplier: Number(supplier),
        warehouse: Number(warehouse),
        // Against an order the server applies the order's currency and rate.
        ...(orderId ? { purchase_order: orderId } : fxPayload(fx, fxInfo)),
        note,
        lines: lines.map((l) => ({
          product: l.id,
          quantity: String(l.qty),
          unit_cost: l.unit_cost === "" ? undefined : l.unit_cost,
          ...(l.tracked ? { lot_number: l.lot.trim(), expiry_date: l.expiry || null } : {}),
        })),
      });
      reset();
      setDone(true);
      onReceived?.();
      if (result.queued) toast.info(t("sync.savedForUpload"));
      else toast.success(t("purchasing.received"));
    } catch (err) {
      const msg =
        errorText(err, t, "purchasing.receivingFailed");
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
          <BarcodeScanInput onScan={addProduct} captureGlobal />
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
                  className="tap flex w-full items-center justify-between px-4 py-2.5 text-start text-sm hover:bg-paper"
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
                <div key={l.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm text-ink">{l.name}</div>
                    <div className="tabular text-xs text-muted">{l.sku}</div>
                    {l.tracked && (
                      <div className="mt-2 flex flex-wrap items-end gap-2">
                        <label className="text-xs text-muted">
                          {t("purchasing.lot")}
                          <Input
                            value={l.lot}
                            onChange={(e) => updateLine(l.id, { lot: e.target.value })}
                            placeholder="LOT-2026-09"
                            aria-label={`${t("purchasing.lot")} ${l.sku}`}
                            className="mt-0.5 w-36"
                          />
                        </label>
                        <label className="text-xs text-muted">
                          {t("purchasing.expiry")}
                          <Input
                            type="date"
                            value={l.expiry}
                            onChange={(e) => updateLine(l.id, { expiry: e.target.value })}
                            aria-label={`${t("purchasing.expiry")} ${l.sku}`}
                            className={`mt-0.5 w-40 ${expiryState(l) === "past" ? "border-danger" : expiryState(l) === "soon" ? "border-warn" : ""}`}
                          />
                        </label>
                        {expiryState(l) === "past" && (
                          <span className="inline-flex items-center gap-1 text-xs text-danger"><AlertTriangle size={12} />{t("purchasing.expiryPastHint")}</span>
                        )}
                        {expiryState(l) === "soon" && (
                          <span className="inline-flex items-center gap-1 text-xs text-warn"><AlertTriangle size={12} />{t("purchasing.expirySoonHint")}</span>
                        )}
                        {!l.lot.trim() && (
                          <span className="text-xs text-muted">{t("purchasing.lotHint")}</span>
                        )}
                      </div>
                    )}
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
          <CurrencyFields
            info={fxInfo}
            fx={fx}
            onChange={setFx}
            locked={orderFx ? { ...orderFx, source: "order" } : null}
          />

          <div className="flex items-center justify-between border-t border-line pt-4">
            <span className="text-sm text-muted">{t("purchasing.goodsValue")}</span>
            <AmountWithBase
              className="text-lg font-medium text-ink"
              amount={total}
              currency={currency}
              rate={rate}
              info={fxInfo}
            />
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
