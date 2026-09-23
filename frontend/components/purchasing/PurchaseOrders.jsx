"use client";

import { useCallback, useEffect, useState } from "react";
import { PackageCheck, Plus, Send, Trash2, XCircle } from "lucide-react";

import { inventory, purchasing } from "@/lib/api";
import { offlineStore } from "@/lib/offlineStore";
import { useI18n } from "../../app/providers/I18nProvider";
import { useToast } from "@/components/ui/Toast";
import Drawer from "@/components/ui/Drawer";
import { Badge, Button, Card, Field, Input, Select } from "@/components/ui/kit";
import { errorText } from "@/lib/errors";
import { SkeletonRows } from "@/components/ui/Skeleton";

const money = (v) =>
  Number(v ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const TONE = { draft: "muted", sent: "accent", confirmed: "ok", partially_received: "warn", received: "ok", cancelled: "danger" };
// What the server allows from each state (mirrors PurchaseOrderViewSet.TRANSITIONS).
const NEXT = {
  draft: ["sent", "confirmed", "cancelled"],
  sent: ["confirmed", "cancelled", "draft"],
  confirmed: ["cancelled"],
};
const OPEN = new Set(["confirmed", "partially_received", "sent"]);

function NewOrderDrawer({ open, onClose, suppliers, onSaved }) {
  const { t } = useI18n();
  const [supplier, setSupplier] = useState("");
  const [expected, setExpected] = useState("");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [lines, setLines] = useState([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => { if (open) { setSupplier(""); setExpected(""); setLines([]); setError(""); } }, [open]);
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
      : [...ls, { product: p.id, sku: p.sku, name: p.name, qty: "1", cost: String(p.cost_price ?? "0") }]);
    setQuery(""); setResults([]);
  };
  const patch = (id, fields) => setLines((ls) => ls.map((l) => (l.product === id ? { ...l, ...fields } : l)));
  const total = lines.reduce((s, l) => s + Number(l.qty || 0) * Number(l.cost || 0), 0);

  async function save() {
    setError("");
    if (!supplier) return setError(t("purchasing.selectSupplierErr"));
    if (!lines.length) return setError(t("purchasing.addProductErr"));
    setBusy(true);
    try {
      const r = await purchasing.createPurchaseOrder({
        supplier: Number(supplier),
        expected_date: expected || null,
        lines: lines.map((l) => ({ product: l.product, quantity_ordered: l.qty, unit_cost: l.cost })),
      });
      onSaved?.(r.data);
      onClose();
    } catch (err) {
      setError(errorText(err, t, "purchasing.saveError"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Drawer open={open} onClose={onClose} title={t("purchasing.po.newTitle")} wide
      footer={<div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>{t("common.cancel")}</Button>
        <Button onClick={save} disabled={busy}>{busy ? t("common.saving") : t("purchasing.po.create")}</Button>
      </div>}>
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t("purchasing.supplier")}>
            <Select value={supplier} onChange={(e) => setSupplier(e.target.value)}>
              <option value="">{t("common.select")}</option>
              {suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </Select>
          </Field>
          <Field label={t("purchasing.po.expected")}>
            <Input type="date" value={expected} onChange={(e) => setExpected(e.target.value)} />
          </Field>
        </div>
        <div className="relative">
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t("purchasing.searchProduct")} />
          {results.length > 0 && (
            <Card className="absolute z-10 mt-1 w-full overflow-hidden">
              {results.map((p) => (
                <button key={p.id} onClick={() => add(p)} className="tap flex w-full items-center justify-between px-4 py-2 text-start text-sm hover:bg-paper">
                  <span><span className="tabular text-muted">{p.sku}</span> {p.name}</span>
                  <span className="tabular text-muted">{money(p.cost_price)}</span>
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
                <div className="w-20"><Input type="number" inputMode="decimal" min="0" value={l.qty} onChange={(e) => patch(l.product, { qty: e.target.value })} aria-label={t("purchasing.qty")} /></div>
                <div className="w-24"><Input type="number" inputMode="decimal" min="0" step="0.01" value={l.cost} onChange={(e) => patch(l.product, { cost: e.target.value })} aria-label={t("purchasing.unitCost")} /></div>
                <div className="tabular w-24 text-end">{money(Number(l.qty || 0) * Number(l.cost || 0))}</div>
                <button onClick={() => setLines((ls) => ls.filter((x) => x.product !== l.product))} className="text-muted hover:text-danger" aria-label={t("common.remove")}><Trash2 size={15} /></button>
              </div>
            ))}
            <div className="flex justify-between px-3 py-2 text-sm font-semibold"><span>{t("common.total")}</span><span className="tabular">{money(total)}</span></div>
          </div>
        )}
        {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      </div>
    </Drawer>
  );
}

/**
 * Purchase orders: the API had the whole state machine (draft → sent →
 * confirmed → partially received → received / cancelled) and receiving
 * could be capped by an order, but no screen ever showed one. This lists
 * them, raises new ones, moves their status, and hands an open order to
 * the receiving screen.
 */
export default function PurchaseOrders({ suppliers, writable, onReceive, refreshKey }) {
  const { t, language } = useI18n();
  const toast = useToast();
  const [rows, setRows] = useState(null);
  const [filter, setFilter] = useState("open");
  const [drawer, setDrawer] = useState(false);
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(() => {
    purchasing.purchaseOrders({ page_size: 200 })
      .then((r) => setRows(r.data.results ?? r.data))
      // Receiving against an order is floor work; the mirror keeps the open
      // orders in reach while the connection is down.
      .catch(() => offlineStore.getAll("purchase_orders").then(setRows).catch(() => setRows([])));
  }, []);
  useEffect(() => { load(); }, [load, refreshKey]);

  async function move(order, status) {
    setBusyId(order.id);
    try { await purchasing.setPurchaseOrderStatus(order.id, status); load(); }
    catch (err) { toast.error(errorText(err, t, "purchasing.po.moveError")); }
    finally { setBusyId(null); }
  }

  const shown = (rows || []).filter((o) => filter === "all" ? true : filter === "open" ? OPEN.has(o.status) || o.status === "draft" : o.status === filter);
  const fmt = (d) => (d ? new Date(d).toLocaleDateString(language === "ar" ? "ar" : "en") : "—");

  return (
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line p-4">
        <div className="flex items-center gap-2">
          <h2 className="font-display text-lg font-semibold">{t("purchasing.po.title")}</h2>
          <Select value={filter} onChange={(e) => setFilter(e.target.value)} className="w-40">
            <option value="open">{t("purchasing.po.filterOpen")}</option>
            <option value="received">{t("purchasing.po.status.received")}</option>
            <option value="cancelled">{t("purchasing.po.status.cancelled")}</option>
            <option value="all">{t("common.all")}</option>
          </Select>
        </div>
        {writable && <Button onClick={() => setDrawer(true)}><Plus size={16} />{t("purchasing.po.new")}</Button>}
      </div>
      {rows === null ? <SkeletonRows /> : shown.length === 0 ? (
        <p className="p-8 text-center text-muted">{t("purchasing.po.empty")}</p>
      ) : (
        <div className="divide-y divide-line">
          {shown.map((o) => {
            const received = o.lines.reduce((s, l) => s + Number(l.received_quantity || 0), 0);
            const ordered = o.lines.reduce((s, l) => s + Number(l.quantity_ordered || 0), 0);
            const canReceive = writable && (o.status === "confirmed" || o.status === "partially_received" || o.status === "sent");
            return (
              <div key={o.id} className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{o.supplier_name}</span>
                    <span className="tabular text-xs text-muted" dir="ltr">PO-{String(o.id).padStart(5, "0")}</span>
                    <Badge tone={TONE[o.status] || "muted"}>{t(`purchasing.po.status.${o.status}`)}</Badge>
                  </div>
                  <div className="mt-0.5 text-xs text-muted">
                    {t("purchasing.po.lines", { count: o.lines.length })} · {t("purchasing.po.progress", { received, ordered })}
                    {o.expected_date && <> · {t("purchasing.po.expectedShort", { date: fmt(o.expected_date) })}</>}
                  </div>
                </div>
                <div className="tabular font-semibold">{money(o.total)}</div>
                {writable && (
                  <div className="flex flex-wrap items-center gap-1">
                    {canReceive && (
                      <Button variant="outline" onClick={() => onReceive?.(o)}><PackageCheck size={15} />{t("purchasing.po.receive")}</Button>
                    )}
                    {(NEXT[o.status] || []).includes("sent") && (
                      <Button variant="ghost" onClick={() => move(o, "sent")} disabled={busyId === o.id}><Send size={15} />{t("purchasing.po.markSent")}</Button>
                    )}
                    {(NEXT[o.status] || []).includes("confirmed") && (
                      <Button variant="ghost" onClick={() => move(o, "confirmed")} disabled={busyId === o.id}>{t("purchasing.po.confirm")}</Button>
                    )}
                    {(NEXT[o.status] || []).includes("cancelled") && (
                      <Button variant="ghost" onClick={() => move(o, "cancelled")} disabled={busyId === o.id} className="text-danger"><XCircle size={15} />{t("purchasing.po.cancel")}</Button>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
      <NewOrderDrawer open={drawer} onClose={() => setDrawer(false)} suppliers={suppliers} onSaved={() => { load(); toast.success(t("purchasing.po.created")); }} />
    </Card>
  );
}
