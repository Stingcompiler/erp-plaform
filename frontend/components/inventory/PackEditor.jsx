"use client";

import { useCallback, useEffect, useState } from "react";
import { Check, Pencil, Plus, RotateCcw, Trash2, X } from "lucide-react";

import { inventory } from "@/lib/api";
import { useI18n } from "../../app/providers/I18nProvider";
import { Button, Input } from "@/components/ui/kit";
import { errorText } from "@/lib/errors";

const EMPTY = { name: "", quantity: "", barcode: "", sale_price: "" };

// Selling units for an existing product: "Carton = 12, barcode, price".
// Saved row by row against /product-packs/ so a manager can add a carton
// without re-saving the product. Only shown once the product exists.
// A pack can be edited in place (name, barcode, price) and an archived one
// restored — re-adding it under the same name is refused by the server.
export default function PackEditor({ product, baseUnit }) {
  const { t } = useI18n();
  const [packs, setPacks] = useState([]);
  const [draft, setDraft] = useState(EMPTY);
  const [editing, setEditing] = useState(null); // { id, name, barcode, sale_price }
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    if (!product?.id) return;
    inventory.packs({ product: product.id }).then((r) => setPacks(r.data.results || r.data)).catch(() => {});
  }, [product?.id]);
  useEffect(() => { load(); }, [load]);

  const run = async (write) => {
    setError("");
    setBusy(true);
    try {
      await write();
      load();
      return true;
    } catch (err) {
      setError(errorText(err, t, "packs.saveError"));
      return false;
    } finally {
      setBusy(false);
    }
  };

  const add = async () => {
    setError("");
    if (!draft.name.trim() || !draft.quantity) return setError(t("packs.needNameQty"));
    const ok = await run(() => inventory.createPack({
      product: product.id,
      name: draft.name.trim(),
      quantity: draft.quantity,
      barcode: draft.barcode.trim(),
      sale_price: draft.sale_price === "" ? null : draft.sale_price,
    }));
    if (ok) setDraft(EMPTY);
  };

  const startEdit = (pack) => {
    setError("");
    setEditing({
      id: pack.id,
      name: pack.name,
      barcode: pack.barcode || "",
      sale_price: pack.sale_price ?? "",
    });
  };

  const saveEdit = async () => {
    if (!editing.name.trim()) return setError(t("packs.needNameQty"));
    const ok = await run(() => inventory.updatePack(editing.id, {
      name: editing.name.trim(),
      barcode: editing.barcode.trim(),
      sale_price: editing.sale_price === "" ? null : editing.sale_price,
    }));
    if (ok) setEditing(null);
  };

  // Archiving frees the pack's barcode on the server; restoring brings the
  // pack back without one (edit it to give it a code again).
  const archive = (pack) => run(() => inventory.updatePack(pack.id, { is_active: false }));
  const restore = (pack) => run(() => inventory.updatePack(pack.id, { is_active: true }));

  if (!product?.id) return null;
  const active = packs.filter((p) => p.is_active !== false);
  const archived = packs.filter((p) => p.is_active === false);
  return (
    <div className="rounded-card border border-line p-3">
      <div className="text-sm font-medium text-ink">{t("packs.title")}</div>
      <p className="mt-1 text-xs text-muted">{t("packs.hint", { unit: baseUnit || t("sales.baseUnit") })}</p>
      {error && <p role="alert" className="mt-2 text-xs text-danger">{error}</p>}
      {active.length > 0 && (
        <ul className="mt-2 divide-y divide-line text-sm">
          {active.map((p) => (
            editing?.id === p.id ? (
              <li key={p.id} className="grid grid-cols-2 gap-2 py-1.5 sm:grid-cols-[1fr_1fr_6rem_auto]">
                <Input aria-label={t("packs.name")} value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })} />
                <Input aria-label={t("packs.barcode")} placeholder={t("packs.barcode")} value={editing.barcode} onChange={(e) => setEditing({ ...editing, barcode: e.target.value })} />
                <Input type="number" inputMode="decimal" min="0" step="0.01" aria-label={t("packs.price")} placeholder={t("packs.price")} value={editing.sale_price} onChange={(e) => setEditing({ ...editing, sale_price: e.target.value })} />
                <span className="flex items-center gap-1">
                  <button type="button" aria-label={t("common.save")} disabled={busy} onClick={saveEdit} className="rounded-control p-1 text-muted hover:text-ok"><Check size={16} /></button>
                  <button type="button" aria-label={t("common.cancel")} disabled={busy} onClick={() => setEditing(null)} className="rounded-control p-1 text-muted hover:text-ink"><X size={16} /></button>
                </span>
              </li>
            ) : (
              <li key={p.id} className="flex items-center justify-between gap-2 py-1.5">
                <span>{p.name} <span className="text-muted">= {Number(p.quantity)} {baseUnit || ""}</span>{p.barcode && <span className="ms-2 font-mono text-xs text-muted">{p.barcode}</span>}</span>
                <span className="flex items-center gap-2">
                  <span className="tabular">{p.effective_price}</span>
                  <button type="button" aria-label={t("common.edit")} disabled={busy} onClick={() => startEdit(p)} className="rounded-control p-1 text-muted hover:text-ink"><Pencil size={14} /></button>
                  <button type="button" aria-label={t("common.remove")} disabled={busy} onClick={() => archive(p)} className="rounded-control p-1 text-muted hover:text-danger"><Trash2 size={14} /></button>
                </span>
              </li>
            )
          ))}
        </ul>
      )}
      {archived.length > 0 && (
        <div className="mt-2">
          <div className="text-xs text-muted">{t("packs.archived")}</div>
          <ul className="divide-y divide-line text-sm text-muted">
            {archived.map((p) => (
              <li key={p.id} className="flex items-center justify-between gap-2 py-1.5">
                <span>{p.name} = {Number(p.quantity)} {baseUnit || ""}</span>
                <button type="button" disabled={busy} onClick={() => restore(p)} className="inline-flex items-center gap-1 rounded-control px-1 text-xs hover:text-ink">
                  <RotateCcw size={13} /> {t("packs.restore")}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-[1fr_5rem_1fr_6rem_auto]">
        <Input placeholder={t("packs.name")} aria-label={t("packs.name")} value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
        <Input type="number" inputMode="decimal" min="0.001" step="0.001" placeholder={t("packs.quantity")} aria-label={t("packs.quantity")} value={draft.quantity} onChange={(e) => setDraft({ ...draft, quantity: e.target.value })} />
        <Input placeholder={t("packs.barcode")} aria-label={t("packs.barcode")} value={draft.barcode} onChange={(e) => setDraft({ ...draft, barcode: e.target.value })} />
        <Input type="number" inputMode="decimal" min="0" step="0.01" placeholder={t("packs.price")} aria-label={t("packs.price")} value={draft.sale_price} onChange={(e) => setDraft({ ...draft, sale_price: e.target.value })} />
        <Button type="button" variant="outline" disabled={busy} onClick={add}><Plus size={14} /> {t("packs.add")}</Button>
      </div>
    </div>
  );
}
