"use client";

import { useCallback, useEffect, useState } from "react";
import { ClipboardCheck, Plus, Trash2 } from "lucide-react";

import { inventory } from "@/lib/api";
import { useAuth } from "../../app/providers/AuthProvider";
import { useI18n } from "../../app/providers/I18nProvider";
import { useToast } from "@/components/ui/Toast";
import Drawer from "@/components/ui/Drawer";
import { Badge, Button, Card, Field, Input, Select } from "@/components/ui/kit";
import { errorText } from "@/lib/errors";

const TONES = { draft: "muted", submitted: "warn", approved: "ok", cancelled: "danger" };

// Periodic stock count: count what is on the shelf, submit (the server
// freezes ledger balances into the sheet), and a manager other than the
// counter approves — which posts the differences as ordinary adjustments.
export default function StockCountPanel({ warehouses, canWrite }) {
  const { t, language } = useI18n();
  const { user } = useAuth();
  const toast = useToast();
  const [rows, setRows] = useState([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(null);
  // The list and the drawer keep their own errors: one shared message used
  // to follow the user into a fresh "new count" drawer before they typed.
  const [error, setError] = useState("");
  const [drawerError, setDrawerError] = useState("");
  const [draft, setDraft] = useState({ warehouse: "", note: "", lines: [] });
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);

  const load = useCallback(() => {
    inventory.stockCounts().then((r) => setRows(r.data.results || r.data)).catch(() => setRows([]));
  }, []);
  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (!query.trim()) { setResults([]); return undefined; }
    const timer = setTimeout(() => {
      inventory.products({ search: query }).then((r) => setResults(r.data.results.slice(0, 6))).catch(() => setResults([]));
    }, 250);
    return () => clearTimeout(timer);
  }, [query]);

  // A lot-tracked product is counted lot by lot: each line names its lot, so
  // the difference is posted to that lot and expiry reports stay right.
  const [lotsByProduct, setLotsByProduct] = useState({});
  const newLine = (product) => ({
    key: crypto.randomUUID(), product: product.id, sku: product.sku, name: product.name,
    tracked: Boolean(product.track_batches), batch: "", counted_quantity: "",
  });
  const addLine = (product) => {
    setDraft((d) => (!product.track_batches && d.lines.some((l) => l.product === product.id))
      ? d
      : { ...d, lines: [...d.lines, newLine(product)] });
    if (product.track_batches && !lotsByProduct[product.id]) {
      inventory.stockBatches({ product: product.id, page_size: 200 })
        .then((r) => setLotsByProduct((m) => ({ ...m, [product.id]: r.data.results || r.data })))
        .catch(() => setLotsByProduct((m) => ({ ...m, [product.id]: [] })));
    }
    setQuery("");
    setResults([]);
  };
  const updateLine = (key, patch) => setDraft((d) => ({ ...d, lines: d.lines.map((x) => (x.key === key ? { ...x, ...patch } : x)) }));

  const fail = (err, setter = setError) => {
    const msg = errorText(err, t, "count.saveError");
    setter(msg);
    toast.error(msg);
  };

  const openNew = () => { setDrawerError(""); setOpen(true); };

  const saveDraft = async () => {
    setDrawerError("");
    if (!draft.warehouse) return setDrawerError(t("count.chooseWarehouse"));
    if (draft.lines.length === 0) return setDrawerError(t("count.addLines"));
    if (draft.lines.some((l) => l.counted_quantity === "")) return setDrawerError(t("count.fillQuantities"));
    if (draft.lines.some((l) => l.tracked && !l.batch)) return setDrawerError(t("count.chooseLot"));
    setBusy("save");
    try {
      await inventory.createStockCount({
        warehouse: Number(draft.warehouse),
        note: draft.note,
        lines: draft.lines.map((l) => ({
          product: l.product, counted_quantity: String(l.counted_quantity),
          ...(l.tracked ? { batch: Number(l.batch) } : {}),
        })),
      });
      setOpen(false);
      setDraft({ warehouse: "", note: "", lines: [] });
      toast.success(t("count.saved"));
      setError("");
      load();
    } catch (err) { fail(err, setDrawerError); } finally { setBusy(null); }
  };

  const run = async (row, action) => {
    setBusy(`${action}-${row.id}`);
    setError("");
    try {
      const fn = { submit: inventory.submitStockCount, approve: inventory.approveStockCount, cancel: inventory.cancelStockCount }[action];
      await fn(row.id);
      toast.success(t(`count.${action}Done`));
      load();
    } catch (err) { fail(err); } finally { setBusy(null); }
  };

  const fmt = (v) => (v ? new Date(v).toLocaleString(language === "ar" ? "ar" : "en", { dateStyle: "medium", timeStyle: "short" }) : "—");

  return (
    <Card className="mb-4 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 font-medium text-ink"><ClipboardCheck size={16} /> {t("count.title")}</div>
        {canWrite && <Button variant="outline" onClick={openNew}><Plus size={16} /> {t("count.new")}</Button>}
      </div>
      <p className="mt-1 text-xs text-muted">{t("count.hint")}</p>
      {error && <p role="alert" className="mt-2 text-sm text-danger">{error}</p>}
      {rows.length > 0 && (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-line text-xs uppercase tracking-wide text-muted">
              <th className="px-2 py-2 text-start">#</th><th className="px-2 py-2 text-start">{t("inventory.warehouse")}</th>
              <th className="px-2 py-2 text-start">{t("common.status")}</th><th className="px-2 py-2 text-start">{t("count.lines")}</th>
              <th className="px-2 py-2 text-start">{t("count.countedBy")}</th><th className="px-2 py-2 text-start">{t("count.variances")}</th><th />
            </tr></thead>
            <tbody>
              {rows.map((row) => {
                const variances = row.lines.filter((l) => l.variance != null && Number(l.variance) !== 0);
                const mine = row.counted_by === user?.id;
                return (
                  <tr key={row.id} className="border-b border-line last:border-0">
                    <td className="tabular px-2 py-2">{row.id}</td>
                    <td className="px-2 py-2">{row.warehouse_name}</td>
                    <td className="px-2 py-2"><Badge tone={TONES[row.status]}>{t(`count.status.${row.status}`)}</Badge></td>
                    <td className="tabular px-2 py-2">{row.lines.length}</td>
                    <td className="px-2 py-2 text-muted">{row.counted_by_name || "—"} · {fmt(row.submitted_at || row.created_at)}</td>
                    <td className="px-2 py-2 text-muted">
                      {row.status === "draft" ? "—" : variances.length === 0 ? t("count.noVariance") : variances.map((l) => `${l.product_sku}: ${Number(l.variance) > 0 ? "+" : ""}${l.variance}`).join(" · ")}
                    </td>
                    <td className="px-2 py-2">
                      <div className="flex justify-end gap-1">
                        {row.status === "draft" && canWrite && <Button variant="outline" disabled={busy === `submit-${row.id}`} onClick={() => run(row, "submit")}>{t("count.submit")}</Button>}
                        {row.can_approve && <Button disabled={busy === `approve-${row.id}`} onClick={() => run(row, "approve")}>{t("count.approve")}</Button>}
                        {row.status === "submitted" && mine && <span className="text-xs text-muted">{t("count.awaitingOther")}</span>}
                        {row.can_approve && row.moved_since > 0 && <span className="text-xs text-warn">{t("count.movedSince", { count: row.moved_since })}</span>}
                        {row.can_cancel && <Button variant="ghost" disabled={busy === `cancel-${row.id}`} onClick={() => run(row, "cancel")}>{t("common.cancel")}</Button>}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <Drawer open={open} onClose={() => setOpen(false)} title={t("count.new")} wide
        footer={<div className="flex gap-2"><Button disabled={busy === "save" || draft.lines.length === 0} onClick={saveDraft}>{t("count.saveDraft")}</Button><Button variant="outline" onClick={() => setOpen(false)}>{t("common.cancel")}</Button></div>}>
        <div className="space-y-4">
          {drawerError && <p role="alert" className="text-sm text-danger">{drawerError}</p>}
          <Field label={t("inventory.warehouse")}>
            <Select value={draft.warehouse} onChange={(e) => setDraft((d) => ({ ...d, warehouse: e.target.value }))}>
              <option value="">{t("common.choose")}</option>
              {warehouses.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
            </Select>
          </Field>
          <Field label={t("count.note")}><Input value={draft.note} maxLength={255} onChange={(e) => setDraft((d) => ({ ...d, note: e.target.value }))} /></Field>
          <Field label={t("count.addProduct")} hint={t("count.addProductHint")}>
            <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t("inventory.searchPlaceholder")} />
          </Field>
          {results.length > 0 && (
            <ul className="divide-y divide-line rounded-card border border-line">
              {results.map((p) => <li key={p.id}><button type="button" className="tap flex w-full items-center justify-between px-3 py-2 text-start text-sm hover:bg-paper" onClick={() => addLine(p)}><span>{p.name}</span><span className="text-muted">{p.sku}</span></button></li>)}
            </ul>
          )}
          {draft.lines.length > 0 && (
            <table className="w-full text-sm">
              <thead><tr className="text-xs uppercase text-muted"><th className="py-1 text-start">{t("inventory.product")}</th><th className="py-1 text-start">{t("count.lot")}</th><th className="py-1 text-start">{t("count.counted")}</th><th /></tr></thead>
              <tbody>
                {draft.lines.map((l) => (
                  <tr key={l.key} className="border-t border-line">
                    <td className="py-2">{l.name} <span className="text-muted">{l.sku}</span></td>
                    <td className="py-2">
                      {l.tracked ? (
                        <div className="flex flex-wrap items-center gap-1">
                          <Select className="w-36" value={l.batch} aria-label={`${t("count.lot")} ${l.sku}`} onChange={(e) => updateLine(l.key, { batch: e.target.value })}>
                            <option value="">{t("common.choose")}</option>
                            {(lotsByProduct[l.product] || []).map((b) => <option key={b.id} value={b.id}>{b.lot_number}{b.expiry_date ? ` · ${b.expiry_date}` : ""}</option>)}
                          </Select>
                          <button type="button" className="tap text-xs text-accent hover:underline" onClick={() => setDraft((d) => ({ ...d, lines: [...d.lines, { ...newLine({ id: l.product, sku: l.sku, name: l.name, track_batches: true }) }] }))}>{t("count.anotherLot")}</button>
                        </div>
                      ) : <span className="text-muted">—</span>}
                    </td>
                    <td className="py-2">
                      <Input type="number" inputMode="decimal" step="0.001" min="0" className="w-28" value={l.counted_quantity} aria-label={`${t("count.counted")} ${l.sku}`}
                        onChange={(e) => updateLine(l.key, { counted_quantity: e.target.value })} />
                    </td>
                    <td className="py-2 text-end"><button type="button" aria-label={t("common.remove")} className="rounded-control p-1 text-muted hover:text-danger" onClick={() => setDraft((d) => ({ ...d, lines: d.lines.filter((x) => x.key !== l.key) }))}><Trash2 size={14} /></button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </Drawer>
    </Card>
  );
}
