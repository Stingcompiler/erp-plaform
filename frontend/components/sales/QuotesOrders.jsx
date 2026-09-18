"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowRightLeft, FileText, Plus, Receipt, Send, Trash2, XCircle } from "lucide-react";

import { inventory, sales } from "@/lib/api";
import { useI18n } from "../../app/providers/I18nProvider";
import { useToast } from "@/components/ui/Toast";
import Drawer from "@/components/ui/Drawer";
import { Badge, Button, Card, Field, Input, Select } from "@/components/ui/kit";

const money = (v) =>
  Number(v ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const QTONE = { draft: "muted", sent: "accent", accepted: "ok", expired: "danger", converted: "ok" };
const OTONE = { draft: "muted", confirmed: "accent", fulfilled: "ok", cancelled: "danger" };

function NewQuotationDrawer({ open, onClose, customers, onSaved }) {
  const { t } = useI18n();
  const [customer, setCustomer] = useState("");
  const [validUntil, setValidUntil] = useState("");
  const [note, setNote] = useState("");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [lines, setLines] = useState([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => { if (open) { setCustomer(""); setValidUntil(""); setNote(""); setLines([]); setError(""); } }, [open]);
  useEffect(() => {
    if (!query.trim()) { setResults([]); return; }
    const timer = setTimeout(() => {
      inventory.products({ search: query }).then((r) => setResults((r.data.results ?? r.data).slice(0, 6))).catch(() => setResults([]));
    }, 250);
    return () => clearTimeout(timer);
  }, [query]);

  const add = (p) => {
    setLines((ls) => ls.find((l) => l.product === p.id)
      ? ls.map((l) => (l.product === p.id ? { ...l, qty: String(Number(l.qty) + 1) } : l))
      : [...ls, { product: p.id, sku: p.sku, name: p.name, qty: "1", price: String(p.sale_price ?? "0") }]);
    setQuery(""); setResults([]);
  };
  const patch = (id, fields) => setLines((ls) => ls.map((l) => (l.product === id ? { ...l, ...fields } : l)));
  const total = lines.reduce((s, l) => s + Number(l.qty || 0) * Number(l.price || 0), 0);

  async function save() {
    setError("");
    if (!customer) return setError(t("quotes.customerRequired"));
    if (!lines.length) return setError(t("sales.searchToAdd"));
    setBusy(true);
    try {
      const r = await sales.createQuotation({
        customer: Number(customer), valid_until: validUntil || null, note,
        lines: lines.map((l) => ({ product: l.product, quantity: l.qty, unit_price: l.price })),
      });
      onSaved?.(r.data); onClose();
    } catch (err) {
      const data = err?.response?.data;
      setError(typeof data === "object" && data ? Object.values(data).flat().join(" ") : t("quotes.saveError"));
    } finally { setBusy(false); }
  }

  return (
    <Drawer open={open} onClose={onClose} title={t("quotes.newTitle")} wide
      footer={<div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>{t("common.cancel")}</Button>
        <Button onClick={save} disabled={busy}>{busy ? t("common.saving") : t("quotes.create")}</Button>
      </div>}>
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t("sales.customer")}>
            <Select value={customer} onChange={(e) => setCustomer(e.target.value)}>
              <option value="">{t("common.select")}</option>
              {customers.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </Select>
          </Field>
          <Field label={t("quotes.validUntil")}>
            <Input type="date" value={validUntil} onChange={(e) => setValidUntil(e.target.value)} />
          </Field>
        </div>
        <div className="relative">
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t("sales.searchProduct")} />
          {results.length > 0 && (
            <Card className="absolute z-10 mt-1 w-full overflow-hidden">
              {results.map((p) => (
                <button key={p.id} onClick={() => add(p)} className="flex w-full items-center justify-between px-4 py-2 text-start text-sm hover:bg-paper">
                  <span><span className="tabular text-muted">{p.sku}</span> {p.name}</span>
                  <span className="tabular text-muted">{money(p.sale_price)}</span>
                </button>
              ))}
            </Card>
          )}
        </div>
        {lines.length > 0 && (
          <div className="divide-y divide-line rounded-card border border-line">
            {lines.map((l) => (
              <div key={l.product} className="flex flex-wrap items-center gap-3 px-3 py-2 text-sm">
                <div className="min-w-0 flex-1"><div className="truncate">{l.name}</div><div className="tabular text-xs text-muted">{l.sku}</div></div>
                <div className="w-20"><Input type="number" inputMode="decimal" min="0" value={l.qty} onChange={(e) => patch(l.product, { qty: e.target.value })} aria-label={t("sales.quantity")} /></div>
                <div className="w-24"><Input type="number" inputMode="decimal" min="0" step="0.01" value={l.price} onChange={(e) => patch(l.product, { price: e.target.value })} aria-label={t("sales.unitPrice")} /></div>
                <div className="tabular w-24 text-end">{money(Number(l.qty || 0) * Number(l.price || 0))}</div>
                <button onClick={() => setLines((ls) => ls.filter((x) => x.product !== l.product))} className="text-muted hover:text-danger" aria-label={t("common.remove")}><Trash2 size={15} /></button>
              </div>
            ))}
            <div className="flex justify-between px-3 py-2 text-sm font-semibold"><span>{t("common.total")}</span><span className="tabular">{money(total)}</span></div>
          </div>
        )}
        <Field label={t("quotes.note")}><Input value={note} onChange={(e) => setNote(e.target.value)} /></Field>
        {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      </div>
    </Drawer>
  );
}

/**
 * Quotations and sales orders: the API had both (with quotation → order
 * conversion) but no screen. Quote, send, accept, convert; confirm the
 * order; then invoice it — the last step hands the order to the POS, which
 * rings it up with source_order so the invoice links back and the order
 * is fulfilled.
 */
export default function QuotesOrders({ customers, writable, onInvoice, refreshKey }) {
  const { t, language } = useI18n();
  const toast = useToast();
  const [quotes, setQuotes] = useState(null);
  const [orders, setOrders] = useState(null);
  const [drawer, setDrawer] = useState(false);
  const [busy, setBusy] = useState(null);

  const load = useCallback(() => {
    sales.quotations({ page_size: 100 }).then((r) => setQuotes(r.data.results ?? r.data)).catch(() => setQuotes([]));
    sales.orders({ page_size: 100 }).then((r) => setOrders(r.data.results ?? r.data)).catch(() => setOrders([]));
  }, []);
  useEffect(() => { load(); }, [load, refreshKey]);

  const run = async (key, fn, okMsg) => {
    setBusy(key);
    try { await fn(); if (okMsg) toast.success(okMsg); load(); }
    catch (err) { toast.error(err?.response?.data?.detail || t("quotes.actionError")); }
    finally { setBusy(null); }
  };
  const fmt = (d) => (d ? new Date(d).toLocaleDateString(language === "ar" ? "ar" : "en") : "—");

  const Row = ({ id, name, ref, status, tone, sub, total, actions }) => (
    <div className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{name}</span>
          <span className="tabular text-xs text-muted" dir="ltr">{ref}</span>
          <Badge tone={tone}>{status}</Badge>
        </div>
        {sub && <div className="mt-0.5 text-xs text-muted">{sub}</div>}
      </div>
      <div className="tabular font-semibold">{money(total)}</div>
      {writable && <div className="flex flex-wrap items-center gap-1">{actions}</div>}
    </div>
  );

  return (
    <div className="space-y-5">
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line p-4">
          <h2 className="flex items-center gap-2 font-display text-lg font-semibold"><FileText size={18} className="text-accent" />{t("quotes.title")}</h2>
          {writable && <Button onClick={() => setDrawer(true)}><Plus size={16} />{t("quotes.new")}</Button>}
        </div>
        {quotes === null ? <p className="p-8 text-center text-muted">{t("common.loading")}</p> : quotes.length === 0 ? (
          <p className="p-8 text-center text-muted">{t("quotes.empty")}</p>
        ) : (
          <div className="divide-y divide-line">
            {quotes.map((q) => (
              <Row key={q.id} name={q.customer_name} ref={`QT-${String(q.id).padStart(5, "0")}`}
                status={t(`quotes.status.${q.status}`)} tone={QTONE[q.status] || "muted"}
                sub={`${t("purchasing.po.lines", { count: q.lines.length })}${q.valid_until ? ` · ${t("quotes.validShort", { date: fmt(q.valid_until) })}` : ""}`}
                total={q.total}
                actions={<>
                  {q.status === "draft" && <Button variant="ghost" onClick={() => run(`q${q.id}`, () => sales.setQuotationStatus(q.id, "sent"))} disabled={busy === `q${q.id}`}><Send size={15} />{t("quotes.markSent")}</Button>}
                  {(q.status === "draft" || q.status === "sent") && <Button variant="ghost" onClick={() => run(`q${q.id}`, () => sales.setQuotationStatus(q.id, "accepted"))} disabled={busy === `q${q.id}`}>{t("quotes.markAccepted")}</Button>}
                  {(q.status === "draft" || q.status === "sent" || q.status === "accepted") && <Button variant="outline" onClick={() => run(`q${q.id}`, () => sales.convertQuotation(q.id), t("quotes.converted"))} disabled={busy === `q${q.id}`}><ArrowRightLeft size={15} />{t("quotes.convert")}</Button>}
                  {(q.status === "draft" || q.status === "sent") && <Button variant="ghost" className="text-danger" onClick={() => run(`q${q.id}`, () => sales.setQuotationStatus(q.id, "expired"))} disabled={busy === `q${q.id}`}><XCircle size={15} />{t("quotes.markExpired")}</Button>}
                </>}
              />
            ))}
          </div>
        )}
      </Card>

      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line p-4">
          <h2 className="flex items-center gap-2 font-display text-lg font-semibold"><Receipt size={18} className="text-accent" />{t("orders.title")}</h2>
          <p className="text-xs text-muted">{t("orders.hint")}</p>
        </div>
        {orders === null ? <p className="p-8 text-center text-muted">{t("common.loading")}</p> : orders.length === 0 ? (
          <p className="p-8 text-center text-muted">{t("orders.empty")}</p>
        ) : (
          <div className="divide-y divide-line">
            {orders.map((o) => (
              <Row key={o.id} name={o.customer_name} ref={`SO-${String(o.id).padStart(5, "0")}`}
                status={t(`orders.status.${o.status}`)} tone={OTONE[o.status] || "muted"}
                sub={`${t("purchasing.po.lines", { count: o.lines.length })}${o.invoice_id ? ` · ${t("orders.invoiced")}` : ""}`}
                total={o.total}
                actions={<>
                  {o.status === "draft" && <Button variant="ghost" onClick={() => run(`o${o.id}`, () => sales.setOrderStatus(o.id, "confirmed"))} disabled={busy === `o${o.id}`}>{t("orders.confirm")}</Button>}
                  {o.status === "confirmed" && <Button variant="outline" onClick={() => onInvoice?.(o)}><Receipt size={15} />{t("orders.invoice")}</Button>}
                  {(o.status === "draft" || o.status === "confirmed") && <Button variant="ghost" className="text-danger" onClick={() => run(`o${o.id}`, () => sales.setOrderStatus(o.id, "cancelled"))} disabled={busy === `o${o.id}`}><XCircle size={15} />{t("orders.cancel")}</Button>}
                </>}
              />
            ))}
          </div>
        )}
      </Card>
      <NewQuotationDrawer open={drawer} onClose={() => setDrawer(false)} customers={customers} onSaved={() => { load(); toast.success(t("quotes.created")); }} />
    </div>
  );
}
