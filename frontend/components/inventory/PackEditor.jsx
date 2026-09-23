"use client";

import { useCallback, useEffect, useState } from "react";
import { Plus, Trash2 } from "lucide-react";

import { inventory } from "@/lib/api";
import { useI18n } from "../../app/providers/I18nProvider";
import { Button, Input } from "@/components/ui/kit";
import { errorText } from "@/lib/errors";

// Selling units for an existing product: "Carton = 12, barcode, price".
// Saved row by row against /product-packs/ so a manager can add a carton
// without re-saving the product. Only shown once the product exists.
export default function PackEditor({ product, baseUnit }) {
  const { t } = useI18n();
  const [packs, setPacks] = useState([]);
  const [draft, setDraft] = useState({ name: "", quantity: "", barcode: "", sale_price: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    if (!product?.id) return;
    inventory.packs({ product: product.id }).then((r) => setPacks(r.data.results || r.data)).catch(() => {});
  }, [product?.id]);
  useEffect(() => { load(); }, [load]);

  const add = async () => {
    setError("");
    if (!draft.name.trim() || !draft.quantity) return setError(t("packs.needNameQty"));
    setBusy(true);
    try {
      await inventory.createPack({
        product: product.id,
        name: draft.name.trim(),
        quantity: draft.quantity,
        barcode: draft.barcode.trim(),
        sale_price: draft.sale_price === "" ? null : draft.sale_price,
      });
      setDraft({ name: "", quantity: "", barcode: "", sale_price: "" });
      load();
    } catch (err) {
      setError(errorText(err, t, "packs.saveError"));
    } finally { setBusy(false); }
  };

  const remove = async (pack) => {
    setBusy(true);
    try { await inventory.updatePack(pack.id, { is_active: false }); load(); }
    catch { setError(t("packs.saveError")); }
    finally { setBusy(false); }
  };

  if (!product?.id) return null;
  const active = packs.filter((p) => p.is_active !== false);
  return (
    <div className="rounded-card border border-line p-3">
      <div className="text-sm font-medium text-ink">{t("packs.title")}</div>
      <p className="mt-1 text-xs text-muted">{t("packs.hint", { unit: baseUnit || t("sales.baseUnit") })}</p>
      {error && <p role="alert" className="mt-2 text-xs text-danger">{error}</p>}
      {active.length > 0 && (
        <ul className="mt-2 divide-y divide-line text-sm">
          {active.map((p) => (
            <li key={p.id} className="flex items-center justify-between gap-2 py-1.5">
              <span>{p.name} <span className="text-muted">= {Number(p.quantity)} {baseUnit || ""}</span>{p.barcode && <span className="ms-2 font-mono text-xs text-muted">{p.barcode}</span>}</span>
              <span className="flex items-center gap-2">
                <span className="tabular">{p.effective_price}</span>
                <button type="button" aria-label={t("common.remove")} disabled={busy} onClick={() => remove(p)} className="rounded-control p-1 text-muted hover:text-danger"><Trash2 size={14} /></button>
              </span>
            </li>
          ))}
        </ul>
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
