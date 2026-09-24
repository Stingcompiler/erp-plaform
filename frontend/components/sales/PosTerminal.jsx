"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, Check, Minus, Plus, Printer, Search, Trash2, ShoppingBag, CreditCard, UserPlus } from "lucide-react";
import CustomerDrawer from "@/components/sales/CustomerDrawer";

import { inventory, sales } from "@/lib/api";
import { useI18n } from "../../app/providers/I18nProvider";
import { useToast } from "@/components/ui/Toast";
import { useSync } from "@/components/sync/SyncProvider";
import { useAuth } from "../../app/providers/AuthProvider";
import DocumentDrawer from "@/components/print/DocumentDrawer";
import { Badge, Button, Card, Field, Input, Select } from "@/components/ui/kit";
import { accountLabel } from "@/lib/bankChannels";
import BarcodeScanInput from "@/components/inventory/BarcodeScanInput";
import { heldCarts } from "@/lib/syncQueue";
import { cacheProducts, searchProductsOffline } from "@/lib/productCache";
import { nextLocalReference } from "@/lib/localReference";
import { errorText } from "@/lib/errors";
import { round2 } from "@/lib/money";
import { localToday } from "@/lib/dates";

const money = (v) =>
  Number(v ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export default function PosTerminal({
  warehouses,
  customers,
  onCustomersChanged,
  initialOrder = null,
  bankAccounts = [],
  shift = null,
  onSold,
}) {
  const { t, language } = useI18n();
  const [warehouse, setWarehouse] = useState("");
  const [customer, setCustomer] = useState("");
  const [newCustomerOpen, setNewCustomerOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [cart, setCart] = useState([]);
  const [sourceOrder, setSourceOrder] = useState(null);
  // "Invoice this order": customer and lines come from the confirmed sales
  // order; checkout carries source_order so the invoice links back and the
  // order is fulfilled server-side.
  useEffect(() => {
    if (!initialOrder) return;
    if (!saleUuid.current) saleUuid.current = crypto.randomUUID();
    setSourceOrder(initialOrder.id);
    setCustomer(String(initialOrder.customer));
    setCart(initialOrder.lines.map((l) => ({
      key: lineKey(l.product, null), id: l.product, sku: l.product_sku, name: l.product_name,
      price: String(l.unit_price), listPrice: String(l.unit_price), qty: String(Number(l.quantity)),
      unit: "", packs: [], packId: "", packQty: 1, onHand: null, expiryStatus: null,
    })));
  }, [initialOrder]);
  const [provisionalDoc, setProvisionalDoc] = useState(null);
  const [method, setMethod] = useState("cash");
  // Store credit: the customer's open credit notes and how much of them
  // this sale draws on. Loaded when a customer is picked; the tendered
  // amount then covers only the rest.
  const [credit, setCredit] = useState(null); // { total, notes }
  const [creditNote, setCreditNote] = useState("");
  const [creditAmount, setCreditAmount] = useState("");
  const [amount, setAmount] = useState("");
  const [bankAccount, setBankAccount] = useState("");
  const [reference, setReference] = useState("");
  const [sender, setSender] = useState("");
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
  const { user, refresh: refreshSession } = useAuth();
  // The tax rate travels with the signed-in user. A till left open (or
  // offline) for days kept the old rate after the owner changed it, so the
  // session is re-read when the till opens and whenever the connection
  // comes back.
  useEffect(() => {
    if (typeof navigator !== "undefined" && navigator.onLine) refreshSession?.();
    const onOnline = () => refreshSession?.();
    window.addEventListener("online", onOnline);
    return () => window.removeEventListener("online", onOnline);
  }, [refreshSession]);
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

  useEffect(() => {
    setCredit(null); setCreditNote(""); setCreditAmount("");
    if (!customer) return undefined;
    let alive = true;
    sales.customerCredit(customer)
      .then((r) => { if (alive && Number(r.data.total) > 0) setCredit(r.data); })
      .catch(() => {});
    return () => { alive = false; };
  }, [customer]);

  const creditApplied = creditNote ? Math.min(round2(Number(creditAmount || 0)), grandTotal) : 0;
  const cashDue = round2(Math.max(0, grandTotal - creditApplied));

  // A line is one product sold in one unit: the same water sold by the
  // piece and by the carton are two lines, so the key carries the pack.
  const lineKey = (productId, packId) => (packId ? `${productId}:p${packId}` : String(productId));

  // Base units the line takes off the shelf, versus what the ledger says is
  // there. Null when the product is not stock-tracked or on_hand is unknown.
  const shortfall = (l) => {
    if (l.onHand === null || l.onHand === undefined) return null;
    const taking = qtyOf(l) * (l.packId ? Number(l.packQty) || 1 : 1);
    const over = taking - Number(l.onHand);
    return over > 0 ? over : 0;
  };

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
          // Warnings only — the sale is never blocked on them (offline-first:
          // what was handed over the counter is a fact to record).
          onHand: p.is_stock_tracked === false ? null : (p.on_hand ?? null),
          expiryStatus: p.expiry_status || null,
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
    setSourceOrder(null);
    try { await heldCarts.remove(restoredId.current); setHeld(await heldCarts.list()); }
    catch { toast.error(t("improvements.heldError")); }
    restoredId.current = null;
    setCart([]);
    setAmount("");
    setCustomer("");
    saleUuid.current = null;
    localRef.current = null;
    setTicketDiscount("");
    setBankAccount(""); setReference(""); setSender(""); setMethod("cash");
  }

  async function checkout() {
    if (checkoutBusy.current || receipt) return;
    setError("");
    if (!warehouse) return setError(t("sales.selectWarehouseErr"));
    if (cart.length === 0) return setError(t("sales.addProductErr"));
    if (!saleUuid.current) saleUuid.current = crypto.randomUUID();
    if (method === "bank_transfer") {
      if (!bankAccount) return setError(t("sales.chooseBankErr"));
      if (!sender.trim()) return setError(t("sales.senderRequired"));
      if (!reference.trim()) return setError(t("sales.referenceRequired"));
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
    const tendered = amount === "" ? cashDue : Number(amount || 0);
    // Nothing tendered is a credit sale: send no payment rather than a
    // payment of zero, which would appear in the ledger as money received.
    const payment = tendered > 0 ? {
      method,
      amount: String(Math.min(tendered, cashDue)),
    } : null;
    // Money left owing is a sale on account, and the server only accepts
    // that against a named customer. Checked here, while the customer is
    // still at the counter: a queued offline sale used to be refused only
    // when it synced, with the cash already in the drawer and nothing left
    // to do but drop it.
    if (!customer && round2(payment ? Number(payment.amount) : 0) < cashDue) {
      return setError(t("sales.partialNeedsCustomer"));
    }
    if (payment && method === "bank_transfer") {
      payment.company_bank_account = Number(bankAccount);
      payment.sender_bank_name = sender.trim();
      payment.transfer_reference = reference.trim();
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
      ...(sourceOrder ? { source_order: sourceOrder } : {}),
      lines: cart.map((l) => ({
        product: l.id,
        ...(l.packId ? { pack: Number(l.packId) } : {}),
        quantity: String(qtyOf(l)),
        // Always the price the customer saw and paid. A queued sale can
        // replay hours later; if the catalogue price moved in between, the
        // server would otherwise re-price the sale, and an embedded cash
        // payment above the new total makes the whole operation fail for
        // ever (or, if the price rose, records the customer as owing).
        unit_price: String(round2(l.price)),
        ...(Number(l.discountPercent || 0) > 0 ? { discount_percent: String(Number(l.discountPercent)) } : {}),
      })),
      ...(ticket > 0 ? { discount_amount: String(round2(ticket)) } : {}),
      // The rate this receipt was computed with, so the server can tell a
      // changed rate from a wrong total (see POSCheckoutSerializer.tax_rate).
      tax_rate: String(taxRate),
      payment,
      ...(creditApplied > 0 ? { apply_credit: { credit_note: Number(creditNote), amount: String(creditApplied) } } : {}),
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
        setReceipt({
          queued: true, reference: op.client_uuid, local_reference: localRef.current,
          total: grandTotal, subtotal: round2(subtotal), tax_amount: round2(taxTotal),
          provisional: {
            doc_type: "invoice", provisional: true,
            number: localRef.current, date: localToday(),
            currency: user?.currency || "",
            issuer: { name: user?.company_name || "" },
            party: customer ? { name: customers.find((c) => String(c.id) === String(customer))?.name } : null,
            lines: cart.map((l, i) => ({
              description: l.name, quantity: String(qtyOf(l)),
              unit_price: l.price, line_total: round2(netLines[i]),
            })),
            subtotal: round2(subtotal), discount: discountTotal, tax: round2(taxTotal),
            total: grandTotal, amount_paid: payment?.amount ?? 0,
            amount_due: round2(grandTotal - Number(payment?.amount || 0)),
          },
        });
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
      const msg =
        errorText(err, t, "sales.checkoutFailed");
      setError(msg);
      toast.error(msg);
      // The owner changed the tax rate since this till loaded: pick up the
      // new rate now, so the totals update and the next attempt goes through.
      if (err?.response?.data?.tax_rate) refreshSession?.();
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
        {/* An offline sale has no server number yet, so a PROVISIONAL receipt
            carrying the local reference is printed from what the till knows;
            once the queue syncs, the confirmed invoice can be printed too. */}
        {receipt.id && (
          <Button
            variant="ghost"
            className="mt-4 w-full"
            onClick={() => setDocId(receipt.id)}
          >
            <Printer size={16} /> {t("doc.print")}
          </Button>
        )}
        {receipt.queued && receipt.provisional && !confirmedId && (
          <Button
            variant="ghost"
            className="mt-4 w-full"
            onClick={() => setProvisionalDoc(receipt.provisional)}
          >
            <Printer size={16} /> {t("improvements.printProvisional")}
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
        <DocumentDrawer
          id={provisionalDoc ? "provisional" : null}
          open={Boolean(provisionalDoc)}
          onClose={() => setProvisionalDoc(null)}
          fetcher={() => Promise.resolve({ data: provisionalDoc })}
          title={t("improvements.provisionalReceipt")}
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
          <BarcodeScanInput onScan={addProduct} captureGlobal />
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
                  className="tap flex w-full items-center justify-between px-4 py-2.5 text-start text-sm hover:bg-paper"
                >
                  <span className="min-w-0">
                    <span className="tabular text-muted">{p.sku}</span>{" "}
                    <span className="text-ink">{p.name}</span>
                    {p.expiry_status === "expired" && <span className="ms-2 text-xs font-medium text-danger">{t("sales.expired")}</span>}
                    {p.expiry_status === "expiring" && <span className="ms-2 text-xs font-medium text-warn">{t("sales.expiring")}</span>}
                  </span>
                  <span className="flex shrink-0 items-center gap-3">
                    {p.is_stock_tracked !== false && p.on_hand !== undefined && (
                      <span className={`tabular text-xs ${Number(p.on_hand) <= 0 ? "text-danger" : "text-muted"}`}>
                        {t("sales.onHand", { qty: Number(p.on_hand) })}
                      </span>
                    )}
                    <span className="tabular text-ink">{money(p.sale_price)}</span>
                  </span>
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
                    {(shortfall(l) > 0 || l.expiryStatus) && (
                      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs">
                        {shortfall(l) > 0 && (
                          <span className={`inline-flex items-center gap-1 ${Number(l.onHand) <= 0 ? "text-danger" : "text-warn"}`}>
                            <AlertTriangle size={12} />
                            {Number(l.onHand) <= 0
                              ? t("sales.outOfStock")
                              : t("sales.exceedsStock", { qty: Number(l.onHand) })}
                          </span>
                        )}
                        {l.expiryStatus === "expired" && (
                          <span className="inline-flex items-center gap-1 text-danger"><AlertTriangle size={12} />{t("sales.expiredLine")}</span>
                        )}
                        {l.expiryStatus === "expiring" && (
                          <span className="inline-flex items-center gap-1 text-warn"><AlertTriangle size={12} />{t("sales.expiringLine")}</span>
                        )}
                      </div>
                    )}
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
            <div className="flex gap-2">
              <Select value={customer} onChange={(e) => setCustomer(e.target.value)}>
                <option value="">{t("sales.walkIn")}</option>
                {customers.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </Select>
              <Button variant="outline" onClick={() => setNewCustomerOpen(true)} aria-label={t("customers.new")} title={t("customers.new")}>
                <UserPlus size={16} />
              </Button>
            </div>
          </Field>
          <CustomerDrawer
            open={newCustomerOpen}
            onClose={() => setNewCustomerOpen(false)}
            onSaved={async (saved) => { await onCustomersChanged?.(); setCustomer(String(saved.id)); }}
          />

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

          {credit && (
            <div className="rounded-card border border-accent/30 bg-accent/5 p-3">
              <label className="flex items-center justify-between gap-3 text-sm">
                <span className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    className="h-4 w-4 accent-accent"
                    checked={Boolean(creditNote)}
                    onChange={(e) => {
                      if (!e.target.checked) { setCreditNote(""); setCreditAmount(""); return; }
                      const first = credit.notes[0];
                      setCreditNote(String(first.id));
                      setCreditAmount(String(Math.min(Number(first.remaining), grandTotal)));
                    }}
                  />
                  {t("sales.useCredit")}
                </span>
                <span className="tabular font-semibold text-accent">{money(credit.total)}</span>
              </label>
              {creditNote && (
                <div className="mt-2 grid grid-cols-2 gap-3">
                  <Select value={creditNote} onChange={(e) => { setCreditNote(e.target.value); const n = credit.notes.find((x) => String(x.id) === e.target.value); if (n) setCreditAmount(String(Math.min(Number(n.remaining), grandTotal))); }} aria-label={t("sales.creditNote")}>
                    {credit.notes.map((n) => <option key={n.id} value={n.id}>{n.number} · {money(n.remaining)}</option>)}
                  </Select>
                  <Input type="number" inputMode="decimal" min="0" step="0.01" value={creditAmount} onChange={(e) => setCreditAmount(e.target.value)} aria-label={t("sales.creditAmount")} className="text-end" />
                </div>
              )}
              {creditApplied > 0 && (
                <div className="mt-2 flex items-center justify-between text-sm">
                  <span className="text-muted">{t("sales.afterCredit")}</span>
                  <span className="tabular font-semibold">{money(cashDue)}</span>
                </div>
              )}
            </div>
          )}

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
                placeholder={money(cashDue)}
              />
            </Field>
          </div>

          {/* Change due. Cash only — there is nothing to hand back on a
              transfer, and showing a figure there would just be noise. */}
          {method === "cash" && amount !== "" && Number(amount) > cashDue && (
            <div className="flex items-center justify-between rounded-card border border-ok/40 bg-ok/5 px-3 py-2">
              <span className="text-sm text-muted">{t("sales.changeDue")}</span>
              <span className="tabular text-lg font-semibold text-ok">
                {money(Number(amount) - cashDue)}
              </span>
            </div>
          )}
          {method === "cash" && amount !== "" && Number(amount) < cashDue && (
            <div className="flex items-center justify-between rounded-card border border-warn/40 bg-warn/5 px-3 py-2">
              <span className="text-sm text-muted">{t("sales.stillOwed")}</span>
              <span className="tabular text-lg font-semibold text-warn">
                {money(cashDue - Number(amount))}
              </span>
            </div>
          )}
          {amount !== "" && Number(amount) < cashDue && !customer && (
            <p className="text-xs text-warn">{t("sales.partialNeedsCustomer")}</p>
          )}

          {method === "bank_transfer" && (
            <div className="grid grid-cols-2 gap-3">
              <Field label={t("sales.receivingAccount")}>
                <Select value={bankAccount} onChange={(e) => setBankAccount(e.target.value)}>
                  <option value="">{t("common.select")}</option>
                  {bankAccounts.map((a) => (
                    <option key={a.id} value={a.id}>
                      {accountLabel(t, a)}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label={t("sales.senderName")}>
                <Input value={sender} onChange={(e) => setSender(e.target.value)} />
              </Field>
              <Field label={t("sales.transferReference")} hint={t("sales.transferReferenceHint")}>
                <Input
                  value={reference}
                  onChange={(e) => setReference(e.target.value.slice(0, 64))}
                  maxLength={64}
                  dir="ltr"
                />
              </Field>
            </div>
          )}

          {error && <p className="text-sm text-danger">{error}</p>}

          {(() => {
            const short = cart.filter((l) => shortfall(l) > 0).length;
            const expired = cart.filter((l) => l.expiryStatus === "expired").length;
            if (!short && !expired) return null;
            return (
              <div role="status" className="flex items-start gap-2 rounded-control border border-warn/40 bg-warn/10 p-3 text-sm text-ink">
                <AlertTriangle size={16} className="mt-0.5 shrink-0 text-warn" />
                <div>
                  {short > 0 && <div>{t("sales.checkoutShortfall", { count: short })}</div>}
                  {expired > 0 && <div>{t("sales.checkoutExpired", { count: expired })}</div>}
                  <div className="mt-0.5 text-xs text-muted">{t("sales.checkoutWarnHint")}</div>
                </div>
              </div>
            );
          })()}

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
