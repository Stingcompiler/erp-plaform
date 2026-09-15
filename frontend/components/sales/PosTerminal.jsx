"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Check, Minus, Plus, Printer, Search, Trash2, ShoppingBag, CreditCard } from "lucide-react";

import { inventory, sales } from "@/lib/api";
import { useI18n } from "../../app/providers/I18nProvider";
import { useToast } from "@/components/ui/Toast";
import { useSync } from "@/components/sync/SyncProvider";
import { useAuth } from "../../app/providers/AuthProvider";
import DocumentDrawer from "@/components/print/DocumentDrawer";
import { Badge, Button, Card, Field, Input, Select } from "@/components/ui/kit";
import BarcodeScanInput from "@/components/inventory/BarcodeScanInput";
import { heldCarts } from "@/lib/syncQueue";
import { cacheProducts, searchProductsOffline } from "@/lib/productCache";
import { nextLocalReference } from "@/lib/localReference";

const money = (v) =>
  Number(v ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export default function PosTerminal({
  warehouses,
  customers,
  bankAccounts = [],
  shift = null,
  onSold,
}) {
  const { t, language } = useI18n();
  const [warehouse, setWarehouse] = useState("");
  const [customer, setCustomer] = useState("");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [cart, setCart] = useState([]);
  const [method, setMethod] = useState("cash");
  const [amount, setAmount] = useState("");
  const [bankAccount, setBankAccount] = useState("");
  const [reference, setReference] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [receipt, setReceipt] = useState(null);
  const [ticketDiscount, setTicketDiscount] = useState("");
  const [docId, setDocId] = useState(null);
  const [error, setError] = useState("");
  const toast = useToast();
  const [held, setHeld] = useState([]);
  const searchRef = useRef(null);
  const amountRef = useRef(null);
  const restoredId = useRef(null);
  const checkoutBusy = useRef(false);
  const keyboardActions = useRef(null);
  const reloadHeld = useCallback(async () => {
    try { setHeld(await heldCarts.list()); } catch { setError(t("improvements.heldError")); }
  }, [t]);
  useEffect(() => { reloadHeld(); }, [reloadHeld]);
  useEffect(() => {
    const onKey = (e) => {
      if (document.querySelector('[role="dialog"]')) return;
      if (e.key === "F2") { e.preventDefault(); searchRef.current?.focus(); }
      if (e.key === "F4") { e.preventDefault(); amountRef.current?.focus(); }
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); keyboardActions.current?.(); }
    };
    const unload = (e) => { if (keyboardActions.current?.hasCart) { e.preventDefault(); e.returnValue=""; } };
    window.addEventListener("keydown", onKey);
    window.addEventListener("beforeunload", unload);
    return () => { window.removeEventListener("keydown", onKey); window.removeEventListener("beforeunload", unload); };
  }, []);
  const { online, enqueue, confirmation, lookupReceipt } = useSync();
  const { user } = useAuth();
  const confirmedId = receipt?.queued ? confirmation(receipt.reference)?.id : null;
  useEffect(() => {
    if (receipt?.queued && !confirmedId) lookupReceipt(receipt.reference);
  }, [receipt, confirmedId, lookupReceipt]);
  useEffect(() => {
    if (!confirmedId) return;
    let cancelled = false;
    sales.invoice(confirmedId).then((res) => { if (!cancelled) setReceipt(res.data); }).catch(() => {});
    return () => { cancelled = true; };
  }, [confirmedId]);

  // One idempotency key per sale — stable across retries, reset after success.
  const saleUuid = useRef(null);
  const localRef = useRef(null);

  useEffect(() => {
    if (warehouses.length && !warehouse) setWarehouse(String(warehouses[0].id));
  }, [warehouses, warehouse]);

  // Debounced product search.
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
          // Mirror what we've seen into the offline catalogue so scanning
          // still resolves during an outage.
          cacheProducts(r.data.results);
        })
        .catch(async (err) => {
          if (err?.response) { setResults([]); return; }
          setResults(await searchProductsOffline(query, 6));
        });
    }, 250);
    return () => clearTimeout(timer);
  }, [query]);

  // Quantity is held as a STRING while the cashier types: turning "1." or
  // "0.2" into a number on every keystroke fights the input (a trailing dot
  // vanishes, a leading zero is eaten) and makes weights unenterable.
  const qtyOf = (l) => {
    const n = Number(l.qty);
    return Number.isFinite(n) && n > 0 ? n : 0;
  };
  const round2 = (n) => Math.round((n + Number.EPSILON) * 100) / 100;
  const lineGross = (l) => round2(Number(l.price || 0) * qtyOf(l));
  const lineDiscount = (l) => {
    const pct = Number(l.discountPercent || 0);
    return pct > 0 ? round2((lineGross(l) * pct) / 100) : 0;
  };
  const lineTotal = (l) => lineGross(l) - lineDiscount(l);
  // Same rules as the server (POSCheckoutSerializer): line discount off the
  // gross, ticket discount spread pro-rata (last line takes the rounding),
  // then per-line tax at the company's flat rate. Mirrored here so what the
  // cashier collects is what the invoice will say.
  const taxRate = Number(user?.tax_rate ?? 0);
  const netBase = cart.reduce((s, l) => s + lineTotal(l), 0);
  const ticket = Math.min(Number(ticketDiscount || 0), netBase);
  let allocated = 0;
  const netLines = cart.map((l, i) => {
    const net = lineTotal(l);
    const share = i === cart.length - 1 ? round2(ticket - allocated) : netBase > 0 ? round2((ticket * net) / netBase) : 0;
    allocated += share;
    return net - share;
  });
  const subtotal = round2(netLines.reduce((s, n) => s + n, 0));
  const discountTotal = round2(cart.reduce((s, l) => s + lineDiscount(l), 0) + ticket);
  const taxTotal = round2(netLines.reduce((s, n) => s + round2((n * taxRate) / 100), 0));
  const grandTotal = round2(subtotal + taxTotal);

  // A line is one product sold in one unit: the same water sold by the
  // piece and by the carton are two lines, so the key carries the pack.
  const lineKey = (productId, packId) => (packId ? `${productId}:p${packId}` : String(productId));

  function addProduct(p, pack = p.scanned_pack || null) {
    if (!saleUuid.current) saleUuid.current = crypto.randomUUID();
    const key = lineKey(p.id, pack?.id);
    const price = pack ? pack.effective_price : String(p.sale_price ?? 0);
    setCart((c) => {
      const found = c.find((l) => l.key === key);
      // A repeat scan of the same item bumps it by one — the till's most
      // common gesture. A weighed item is typed over instead.
      if (found) {
        return c.map((l) =>
          l.key === key ? { ...l, qty: String(qtyOf(l) + 1) } : l,
        );
      }
      return [
        ...c,
        {
          key,
          id: p.id,
          sku: p.sku,
          name: p.name,
          price: String(price),
          listPrice: String(price),
          qty: "1",
          unit: pack ? pack.name : (p.unit_name || ""),
          packs: p.packs || [],
          packId: pack ? String(pack.id) : "",
          packQty: pack ? Number(pack.quantity) : 1,
        },
      ];
    });
    setQuery("");
    setResults([]);
  }

  // Switching a line between the base unit and a pack re-keys it and resets
  // its price to that unit's list price; the typed quantity is kept because
  // "3" usually still means three of whatever the cashier now picked.
  const changePack = (key, packId) =>
    setCart((c) => {
      const line = c.find((l) => l.key === key);
      if (!line) return c;
      const pack = line.packs.find((x) => String(x.id) === String(packId)) || null;
      const nextKey = lineKey(line.id, pack?.id);
      if (nextKey !== key && c.some((l) => l.key === nextKey)) return c; // already a line for that unit
      const price = pack ? pack.effective_price : line.basePrice ?? line.listPrice;
      return c.map((l) => l.key === key ? {
        ...l, key: nextKey, packId: pack ? String(pack.id) : "", packQty: pack ? Number(pack.quantity) : 1,
        unit: pack ? pack.name : (l.baseUnit ?? l.unit), price: String(price), listPrice: String(price),
        basePrice: l.basePrice ?? l.listPrice, baseUnit: l.baseUnit ?? l.unit,
      } : l);
    });

  const patchLine = (key, patch) =>
    setCart((c) => c.map((l) => (l.key === key ? { ...l, ...patch } : l)));

  const bumpQty = (key, delta) =>
    setCart((c) =>
      c.map((l) =>
        l.key === key ? { ...l, qty: String(Math.max(0, qtyOf(l) + delta)) } : l,
      ),
    );

  const removeLine = (key) => setCart((c) => c.filter((l) => l.key !== key));

  async function holdCart() {
    if (!cart.length || checkoutBusy.current) return;
    try {
      await heldCarts.save({ id: restoredId.current, cart, warehouse, customer, method, amount,
        bankAccount, reference, sale_uuid: saleUuid.current });
      restoredId.current = null;
      await resetSale();
      toast.info(t("improvements.heldSaved"));
    } catch { setError(t("improvements.heldError")); }
  }
  function resumeCart(row) {
    if (cart.length) return setError(t("improvements.heldConflict"));
    setCart(row.cart); setWarehouse(row.warehouse); setCustomer(row.customer);
    setMethod(row.method); setAmount(row.amount); setBankAccount(row.bankAccount);
    setReference(row.reference); saleUuid.current = row.sale_uuid;
    restoredId.current = row.id; setError("");
    // Keep the saved copy until the sale completes or is held again.
  }
  async function resetSale() {
    try { await heldCarts.remove(restoredId.current); setHeld(await heldCarts.list()); }
    catch { toast.error(t("improvements.heldError")); }
    restoredId.current = null;
    setCart([]);
    setAmount("");
    setCustomer("");
    saleUuid.current = null;
    localRef.current = null;
    setTicketDiscount("");
    setBankAccount(""); setReference(""); setMethod("cash");
  }

  async function checkout() {
    if (checkoutBusy.current || receipt) return;
    setError("");
    if (!warehouse) return setError(t("sales.selectWarehouseErr"));
    if (cart.length === 0) return setError(t("sales.addProductErr"));
    if (!saleUuid.current) saleUuid.current = crypto.randomUUID();
    if (method === "bank_transfer" && !bankAccount) {
      return setError(t("sales.chooseBankErr"));
    }

    // Built once, before the try, so the offline fallback in `catch` queues
    // exactly what the online path would have sent. Rebuilding it there had
    // already drifted — it omitted the shift, so a sale recovered from a flaky
    // connection would have belonged to no drawer.
    // What the cashier types is what the customer HANDED OVER, which for cash
    // is routinely more than the bill. Recording that as the payment would
    // overpay the invoice and leave a phantom credit on the account, so the
    // payment is capped at what is owed and the surplus is handed back as
    // change. Typing less than the bill still records a partial payment.
    const tendered = amount === "" ? grandTotal : Number(amount || 0);
    const payment = {
      method,
      amount: String(Math.min(tendered, grandTotal)),
    };
    if (method === "bank_transfer") {
      payment.company_bank_account = Number(bankAccount);
      if (reference) payment.reference_last4 = reference;
    }
    // Printed on the receipt immediately; the server keeps it next to the
    // invoice number it assigns, so an offline receipt stays traceable.
    localRef.current ||= nextLocalReference(user?.branch_code || warehouses.find((w) => String(w.id) === String(warehouse))?.code);
    const checkoutPayload = {
      client_uuid: saleUuid.current,
      local_reference: localRef.current,
      // Business time of the sale. For a queued offline sale this is what
      // lands on the invoice, the stock movements, and the payment when it
      // finally syncs — not the moment the connection came back.
      occurred_at: new Date().toISOString(),
      warehouse: Number(warehouse),
      customer: customer ? Number(customer) : null,
      lines: cart.map((l) => ({
        product: l.id,
        ...(l.packId ? { pack: Number(l.packId) } : {}),
        quantity: String(qtyOf(l)),
        // Only sent when the cashier actually overrode it, so an untouched
        // line keeps following the catalogue price rather than freezing
        // today's value into the invoice.
        ...(String(l.price) !== String(l.listPrice)
          ? { unit_price: String(Number(l.price || 0)) }
          : {}),
        ...(Number(l.discountPercent || 0) > 0 ? { discount_percent: String(Number(l.discountPercent)) } : {}),
      })),
      ...(ticket > 0 ? { discount_amount: String(round2(ticket)) } : {}),
      payment,
      // Stamped from the client, not the server clock: an offline sale can
      // sync after its shift closed and must still land in the drawer that
      // actually took the cash.
      ...(shift ? { shift: shift.id } : {}),
    };

    checkoutBusy.current = true;
    setSubmitting(true);
    const saveOffline = async () => {
      try {
        const op = await enqueue("pos_checkout", checkoutPayload);
        setReceipt({ queued: true, reference: op.client_uuid, local_reference: localRef.current, total: grandTotal, subtotal: round2(subtotal), tax_amount: round2(taxTotal) });
        resetSale(); onSold?.(); toast.info(t("sales.savedOffline"));
      } catch { setError(t("improvements.storageSale")); toast.error(t("improvements.storageSale")); }
    };
    try {

      // Offline: queue the sale (same client_uuid keeps it idempotent) and
      // let the sync layer drain it when connectivity returns.
      // `online` comes from a real reachability probe, not navigator.onLine
      // alone: a router with no upstream must not make the till wait out a
      // full request timeout before every sale.
      if (!online) {
        await saveOffline();
        return;
      }

      const res = await sales.checkout(checkoutPayload);
      setReceipt(res.data);
      resetSale();
      onSold?.();
      toast.success(t("sales.saleRecorded"));
    } catch (err) {
      // A network error while "online" (e.g. flaky connection): fall back to
      // the offline queue rather than losing the sale.
      if (err?.code === "ERR_NETWORK" || !err?.response) {
        await saveOffline();
        return;
      }
      const data = err?.response?.data;
      const msg =
        typeof data === "object" && data
          ? Object.values(data).flat().join(" ")
          : t("sales.checkoutFailed");
      setError(msg);
      toast.error(msg);
    } finally {
      checkoutBusy.current = false;
      setSubmitting(false);
    }
  }

  keyboardActions.current = checkout;
  keyboardActions.current.hasCart = cart.length > 0;

  if (receipt) {
    return (
      <Card className="mx-auto max-w-md p-6 text-center">
        <div className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-ok/10 text-ok">
          <Check />
        </div>
        <h2 className="mt-3 font-display text-xl font-semibold">{t(receipt.queued ? "improvements.queuedSale" : "sales.saleRecorded")}</h2>
        <p className="mt-1 text-muted">
          {receipt.queued ? t("improvements.queuedHint") : t("sales.invoice")}
          <span className="tabular block break-all text-ink">{receipt.queued ? receipt.local_reference : (receipt.number_display || receipt.number)}</span>
          {receipt.queued && <span className="mt-1 block font-mono text-[11px] text-muted">{receipt.reference}</span>}
        </p>
        <div className="tabular mt-4 text-3xl font-medium text-ink">{money(receipt.total)}</div>
        {!receipt.queued && <div className="mt-1 text-sm text-muted">
          {t("sales.tax")} {money(receipt.tax_amount)} · {t("sales.subtotal")} {money(receipt.subtotal)}
        </div>}
        {/* An offline sale has no server id yet, so there is nothing to fetch a
            document for — the till still closes the sale, it just can't print
            until the queued invoice syncs. */}
        {receipt.id && (
          <Button
            variant="ghost"
            className="mt-4 w-full"
            onClick={() => setDocId(receipt.id)}
          >
            <Printer size={16} /> {t("doc.print")}
          </Button>
        )}
        <Button className="mt-2 w-full" onClick={() => setReceipt(null)}>
          {t("sales.newSale")}
        </Button>

        <DocumentDrawer
          id={docId}
          open={Boolean(docId)}
          onClose={() => setDocId(null)}
          fetcher={sales.invoiceDocument}
          title={t("sales.invoice")}
        />
      </Card>
    );
  }

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Button variant="outline" onClick={holdCart} disabled={!cart.length || submitting}>{t("improvements.hold")}</Button>
        <span className="text-xs text-muted">{t("improvements.holdHint")}</span>
      </div>
      {held.length > 0 && <details className="mb-4 rounded-card border border-line bg-surface p-3">
        <summary className="cursor-pointer text-sm font-medium">{t("improvements.held")} ({held.length})</summary>
        <ul className="mt-3 space-y-2">{held.map((row) => <li key={row.id} className="flex items-center justify-between gap-3 text-sm">
          <span>{row.cart[0]?.name} · {row.cart.length} · {new Date(row.saved_at).toLocaleTimeString(language === "ar" ? "ar" : "en")}</span>
          <Button variant="outline" onClick={() => resumeCart(row)} disabled={submitting}>{t("improvements.resume")}</Button>
        </li>)}</ul>
      </details>}
      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
      {/* Catalogue / search */}
      <div>
        {/* Selling with no drawer open is allowed — blocking it would stop a
            shop trading — but the cash then reconciles against nothing, so say
            so plainly rather than letting it pass silently. */}
        {!shift && (
          <div className="mb-3 rounded-card border border-warn/40 bg-warn/5 px-3 py-2 text-sm text-warn">
            {t("till.noShiftWarning")}
          </div>
        )}
        {/* Scan first: the till's primary input. Falls back to the search
            below for products without a barcode. */}
        <div className="mb-3">
          <BarcodeScanInput onScan={addProduct} />
        </div>
        <div className="relative">
          <Search size={16} className="pointer-events-none absolute inset-y-0 start-3 my-auto text-muted" />
          <Input
            ref={searchRef} aria-label={t("sales.searchToAddShort")}
            placeholder={t("sales.searchToAddShort")}
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
                  <span className="tabular text-ink">{money(p.sale_price)}</span>
                </button>
              ))}
            </Card>
          )}
        </div>

        <Card className="mt-4">
          {cart.length === 0 ? (
            <div className="flex min-h-64 flex-col items-center justify-center gap-4 px-6 py-12 text-center text-sm text-muted">
              <span className="grid h-16 w-16 place-items-center rounded-2xl border border-accent/15 bg-accent/5 text-accent"><ShoppingBag size={28} strokeWidth={1.5} /></span>
              {t("sales.searchToAdd")}
            </div>
          ) : (
            <div className="divide-y divide-line">
              {cart.map((l) => (
                <div key={l.key} className="flex flex-wrap items-center gap-3 px-4 py-3">
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm text-ink">{l.name}</div>
                    <div className="tabular text-xs text-muted">
                      {l.sku}
                      {l.packs?.length > 0 ? (
                        <select
                          value={l.packId}
                          onChange={(e) => changePack(l.key, e.target.value)}
                          aria-label={t("sales.sellBy")}
                          className="ms-1 rounded-control border border-line bg-surface px-1 py-0.5 text-xs text-ink"
                        >
                          <option value="">{(l.baseUnit ?? (l.packId ? "" : l.unit)) || t("sales.baseUnit")}</option>
                          {l.packs.filter((x) => x.is_active !== false).map((x) => (
                            <option key={x.id} value={x.id}>{x.name} ({Number(x.quantity)})</option>
                          ))}
                        </select>
                      ) : (l.unit ? ` · ${l.unit}` : "")}
                      {l.packId && <span className="ms-1">= {Number(l.packQty) * qtyOf(l)} {l.baseUnit || ""}</span>}
                      {String(l.price) !== String(l.listPrice) && (
                        <span className="ms-1 text-warn">
                          {t("sales.priceChanged", { price: money(l.listPrice) })}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Typed, not stepped: a grocery sells 1.250 kg of tomatoes,
                      which +1/−1 buttons alone can never express. The buttons
                      stay for the common whole-unit case. */}
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => bumpQty(l.key, -1)}
                      aria-label={t("sales.decrease")}
                      className="rounded-control border border-line p-1 text-muted hover:bg-paper"
                    >
                      <Minus size={14} />
                    </button>
                    <Input
                      type="number"
                      inputMode="decimal"
                      step="0.001"
                      min="0"
                      value={l.qty}
                      onChange={(e) => patchLine(l.key, { qty: e.target.value })}
                      aria-label={t("sales.quantity")}
                      className="w-20 text-center"
                    />
                    <button
                      onClick={() => bumpQty(l.key, 1)}
                      aria-label={t("sales.increase")}
                      className="rounded-control border border-line p-1 text-muted hover:bg-paper"
                    >
                      <Plus size={14} />
                    </button>
                  </div>

                  <div className="w-24">
                    <Input
                      type="number"
                      inputMode="decimal"
                      step="0.01"
                      min="0"
                      value={l.price}
                      onChange={(e) => patchLine(l.key, { price: e.target.value })}
                      aria-label={t("sales.unitPrice")}
                      className="text-end"
                    />
                  </div>

                  <div className="w-16">
                    <Input
                      type="number"
                      inputMode="decimal"
                      step="0.5"
                      min="0"
                      max="100"
                      value={l.discountPercent || ""}
                      placeholder="%"
                      onChange={(e) => patchLine(l.key, { discountPercent: e.target.value })}
                      aria-label={t("sales.lineDiscount")}
                      className="text-end"
                    />
                  </div>

                  <div className="tabular w-20 text-end text-sm font-medium text-ink">
                    {money(lineTotal(l))}
                  </div>
                  <button
                    onClick={() => removeLine(l.key)}
                    className="text-muted hover:text-danger"
                    aria-label={t("sales.remove")}
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {/* Checkout panel */}
      <Card className="h-fit border-accent/20 p-5 xl:sticky xl:top-24">
        <div className="mb-5 flex items-center gap-2 border-b border-line pb-4 text-sm font-semibold"><CreditCard size={18} className="text-accent" />{t("sales.payment")}</div>
        <div className="space-y-4">
          {/* A shop with one store shouldn't be asked which store, on every
              single sale. The value is still sent — only the question is
              dropped. */}
          {warehouses.length > 1 ? (
            <Field label={t("sales.warehouse")}>
              <Select value={warehouse} onChange={(e) => setWarehouse(e.target.value)}>
                {warehouses.map((w) => (
                  <option key={w.id} value={w.id}>
                    {w.name}
                  </option>
                ))}
              </Select>
            </Field>
          ) : (
            warehouses.length === 0 && (
              <p className="rounded-card border border-warn/40 bg-warn/5 px-3 py-2 text-sm text-warn">
                {t("sales.noWarehouses")}
              </p>
            )
          )}
          <Field label={t("sales.customer")} hint={t("sales.customerHint")}>
            <Select value={customer} onChange={(e) => setCustomer(e.target.value)}>
              <option value="">{t("sales.walkIn")}</option>
              {customers.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </Select>
          </Field>

          <div className="rounded-xl bg-accent/5 p-4">
            <div className="flex items-center justify-between gap-3 text-sm text-muted">
              <span>{t("sales.subtotal")}</span>
              <span className="tabular">{money(subtotal)}</span>
            </div>
            <div className="mt-1 flex items-center justify-between gap-3 text-sm text-muted">
              <span>{t("sales.ticketDiscount")}</span>
              <Input
                type="number"
                inputMode="decimal"
                step="0.01"
                min="0"
                value={ticketDiscount}
                onChange={(e) => setTicketDiscount(e.target.value)}
                aria-label={t("sales.ticketDiscount")}
                className="w-28 text-end"
              />
            </div>
            {discountTotal > 0 && (
              <div className="mt-1 flex items-center justify-between gap-3 text-sm text-muted">
                <span>{t("sales.discountTotal")}</span>
                <span className="tabular">−{money(discountTotal)}</span>
              </div>
            )}
            {taxRate > 0 && (
              <div className="mt-1 flex items-center justify-between gap-3 text-sm text-muted">
                <span>{t("sales.tax")} ({taxRate}%)</span>
                <span className="tabular">{money(taxTotal)}</span>
              </div>
            )}
            <div className="mt-2 flex items-center justify-between gap-3 border-t border-line pt-2">
              <span className="text-sm text-muted">{t("common.total")}</span>
              <span className="tabular text-2xl font-semibold text-ink">{money(grandTotal)}</span>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Field label={t("sales.payment")}>
              <Select value={method} onChange={(e) => setMethod(e.target.value)}>
                <option value="cash">{t("common.cash")}</option>
                <option value="bank_transfer">{t("common.bankTransfer")}</option>
              </Select>
            </Field>
            <Field label={t("sales.tendered")} hint={t("sales.amountHint")}>
              <Input
                type="number"
                inputMode="decimal"
                ref={amountRef}
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                placeholder={money(grandTotal)}
              />
            </Field>
          </div>

          {/* Change due. Cash only — there is nothing to hand back on a
              transfer, and showing a figure there would just be noise. */}
          {method === "cash" && amount !== "" && Number(amount) > grandTotal && (
            <div className="flex items-center justify-between rounded-card border border-ok/40 bg-ok/5 px-3 py-2">
              <span className="text-sm text-muted">{t("sales.changeDue")}</span>
              <span className="tabular text-lg font-semibold text-ok">
                {money(Number(amount) - grandTotal)}
              </span>
            </div>
          )}
          {method === "cash" && amount !== "" && Number(amount) < grandTotal && (
            <div className="flex items-center justify-between rounded-card border border-warn/40 bg-warn/5 px-3 py-2">
              <span className="text-sm text-muted">{t("sales.stillOwed")}</span>
              <span className="tabular text-lg font-semibold text-warn">
                {money(grandTotal - Number(amount))}
              </span>
            </div>
          )}

          {method === "bank_transfer" && (
            <div className="grid grid-cols-2 gap-3">
              <Field label={t("sales.bankName")}>
                <Select value={bankAccount} onChange={(e) => setBankAccount(e.target.value)}>
                  <option value="">{t("common.select")}</option>
                  {bankAccounts.map((a) => (
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
                  placeholder="1234"
                />
              </Field>
            </div>
          )}

          {error && <p className="text-sm text-danger">{error}</p>}

          <Button className="min-h-12 w-full" onClick={checkout} disabled={submitting || cart.length === 0}>
            {submitting ? t("sales.recording") : t("sales.completeSale")}
          </Button>
          <div className="text-center">
            <Badge tone="muted">{t("sales.manualOffline")}</Badge>
          </div>
        </div>
      </Card>
    </div>
    </div>
  );
}
