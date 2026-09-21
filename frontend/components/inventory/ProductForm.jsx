"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Barcode, Plus, X } from "lucide-react";

import { inventory } from "@/lib/api";
import { useI18n } from "../../app/providers/I18nProvider";
import { ean13Svg, isValidEan13 } from "@/lib/ean13";
import Drawer from "@/components/ui/Drawer";
import { Button, Field, Input, Select } from "@/components/ui/kit";
import PackEditor from "@/components/inventory/PackEditor";

const EMPTY = {
  sku: "",
  name: "",
  category: "",
  brand: "",
  unit: "",
  barcode: "",
  cost_price: "0",
  sale_price: "0",
  reference_price: "",
  reference_cost: "",
  reorder_level: "0",
  track_batches: false,
  is_stock_tracked: true,
};

// A select with an inline "+ Add new" affordance so reference data (category,
// brand, unit) can be created without leaving the product form — no dead
// dropdowns.
function PickerWithAdd({ label, addLabel, placeholder, options, value, onChange, onCreate }) {
  const { t } = useI18n();
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  async function create() {
    if (!name.trim()) return;
    setBusy(true);
    try {
      const created = await onCreate(name.trim());
      if (created?.id) onChange(String(created.id));
      setName("");
      setAdding(false);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Field label={label}>
      {adding ? (
        <div className="flex gap-2">
          <Input
            autoFocus
            placeholder={placeholder}
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && create()}
          />
          <Button variant="outline" onClick={create} disabled={busy || !name.trim()} className="shrink-0">
            {t("common.add")}
          </Button>
          <Button variant="ghost" onClick={() => setAdding(false)} className="shrink-0 px-2">
            <X size={16} />
          </Button>
        </div>
      ) : (
        <div className="flex gap-2">
          <Select value={value} onChange={(e) => onChange(e.target.value)}>
            <option value="">{t("common.none")}</option>
            {options.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
          </Select>
          <Button variant="outline" onClick={() => setAdding(true)} className="shrink-0 px-2.5" title={addLabel}>
            <Plus size={16} />
          </Button>
        </div>
      )}
    </Field>
  );
}

export default function ProductForm({ open, onClose, onSaved, product, exchangeRate, referenceCurrency }) {
  const { t } = useI18n();
  const [form, setForm] = useState(EMPTY);
  const [categories, setCategories] = useState([]);
  const [brands, setBrands] = useState([]);
  const [units, setUnits] = useState([]);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const editing = Boolean(product);

  // Live preview of the scannable symbol (only valid EAN-13 renders).
  const barcodePreview = useMemo(() => ean13Svg(form.barcode), [form.barcode]);
  // Thirteen digits that fail the checksum is almost always a typo in a
  // hand-copied label; say so, but let a deliberate non-EAN code through.
  const checksumWarning = /^\d{13}$/.test(form.barcode.trim()) && !isValidEan13(form.barcode.trim());

  async function generateBarcode() {
    setGenerating(true);
    setError("");
    try {
      const res = await inventory.generateBarcode(product.id);
      setForm((f) => ({ ...f, barcode: res.data.barcode }));
    } catch (err) {
      const data = err?.response?.data;
      setError(data?.detail || t("inventory.saveError"));
    } finally {
      setGenerating(false);
    }
  }

  const loadRefs = useCallback(() => {
    inventory.categories().then((r) => setCategories(r.data.results || r.data)).catch(() => {});
    inventory.brands().then((r) => setBrands(r.data.results || r.data)).catch(() => {});
    inventory.units().then((r) => setUnits(r.data.results || r.data)).catch(() => {});
  }, []);

  useEffect(() => {
    if (!open) return;
    loadRefs();
    if (product) {
      setForm({
        sku: product.sku || "",
        name: product.name || "",
        category: product.category || "",
        brand: product.brand || "",
        unit: product.unit || "",
        barcode: product.barcode || "",
        cost_price: String(product.cost_price ?? "0"),
        sale_price: String(product.sale_price ?? "0"),
        reference_price: product.reference_price == null ? "" : String(product.reference_price),
        reference_cost: product.reference_cost == null ? "" : String(product.reference_cost),
        reorder_level: String(product.reorder_level ?? "0"),
        track_batches: Boolean(product.track_batches),
        is_stock_tracked: product.is_stock_tracked !== false,
      });
    } else {
      setForm(EMPTY);
    }
    setError("");
  }, [product, open, loadRefs]);

  const set = (key) => (e) =>
    setForm((f) => ({
      ...f,
      [key]: e.target.type === "checkbox" ? e.target.checked : e.target.value,
    }));
  const setField = (key) => (v) => setForm((f) => ({ ...f, [key]: v }));

  async function save() {
    setError("");
    setSaving(true);
    const body = {
      ...form,
      category: form.category || null,
      brand: form.brand || null,
      unit: form.unit || null,
      reference_price: form.reference_price === "" ? null : form.reference_price,
      reference_cost: form.reference_cost === "" ? null : form.reference_cost,
    };
    try {
      if (editing) await inventory.updateProduct(product.id, body);
      else await inventory.createProduct(body);
      onSaved();
      onClose();
    } catch (err) {
      const data = err?.response?.data;
      setError(
        typeof data === "object" ? Object.values(data).flat().join(" ") : t("inventory.saveError")
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={editing ? t("inventory.editProduct") : t("inventory.newProduct")}
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button onClick={save} disabled={saving || !form.sku || !form.name}>
            {saving ? t("common.saving") : editing ? t("users.saveChanges") : t("inventory.createProduct")}
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("inventory.sku")}>
            <Input value={form.sku} onChange={set("sku")} disabled={editing} />
          </Field>
          <Field label={t("inventory.reorderLevel")}>
            <Input type="number" value={form.reorder_level} onChange={set("reorder_level")} />
          </Field>
        </div>
        <Field label={t("common.name")}>
          <Input value={form.name} onChange={set("name")} />
        </Field>
        <Field
          label={t("inventory.barcode")}
          hint={barcodePreview ? undefined : t("inventory.scanHint")}
          error={checksumWarning ? t("inventory.barcodeChecksum") : undefined}
        >
          <div className="flex gap-2">
            <Input value={form.barcode} onChange={set("barcode")} />
            {editing && !form.barcode && (
              <Button variant="outline" onClick={generateBarcode} disabled={generating} className="shrink-0">
                <Barcode size={16} />
                {generating ? t("common.saving") : t("inventory.generateBarcode")}
              </Button>
            )}
          </div>
          {barcodePreview && (
            <div
              className="mt-2 text-ink"
              dangerouslySetInnerHTML={{ __html: barcodePreview }}
            />
          )}
        </Field>

        <PickerWithAdd
          label={t("inventory.category")}
          addLabel={t("inventory.addNew")}
          placeholder={t("inventory.categoryName")}
          options={categories}
          value={form.category}
          onChange={setField("category")}
          onCreate={async (name) => {
            const r = await inventory.createCategory({ name });
            loadRefs();
            return r.data;
          }}
        />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <PickerWithAdd
            label={t("inventory.brand")}
            addLabel={t("inventory.addNew")}
            placeholder={t("inventory.brandName")}
            options={brands}
            value={form.brand}
            onChange={setField("brand")}
            onCreate={async (name) => {
              const r = await inventory.createBrand({ name });
              loadRefs();
              return r.data;
            }}
          />
          <PickerWithAdd
            label={t("inventory.unit")}
            addLabel={t("inventory.addNew")}
            placeholder={t("inventory.unitName")}
            options={units}
            value={form.unit}
            onChange={setField("unit")}
            onCreate={async (name) => {
              const r = await inventory.createUnit({ name });
              loadRefs();
              return r.data;
            }}
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Field label={t("inventory.costPrice")}>
            <Input type="number" value={form.cost_price} onChange={set("cost_price")} />
          </Field>
          <Field label={t("inventory.salePrice")}>
            <Input type="number" value={form.sale_price} onChange={set("sale_price")} />
          </Field>
        </div>
        <Field
          label={t("inventory.referencePrice", { currency: referenceCurrency || "USD" })}
          hint={
            form.reference_price !== "" && Number(exchangeRate) > 0
              ? t("inventory.referencePriceHint", {
                  price: (Number(form.reference_price) * Number(exchangeRate)).toLocaleString(
                    undefined, { maximumFractionDigits: 2 },
                  ),
                })
              : t("inventory.referencePriceEmptyHint")
          }
        >
          <div className="flex items-center gap-2">
            <Input
              type="number" inputMode="decimal" min="0" step="0.0001"
              value={form.reference_price} onChange={set("reference_price")} className="w-40"
            />
            {form.reference_price !== "" && Number(exchangeRate) > 0 && (
              <Button
                type="button" variant="ghost"
                onClick={() =>
                  setForm((f) => ({
                    ...f,
                    sale_price: String(Math.round(Number(f.reference_price) * Number(exchangeRate) * 100) / 100),
                  }))
                }
              >
                {t("inventory.applyReferencePrice")}
              </Button>
            )}
          </div>
        </Field>
        <Field
          label={t("inventory.referenceCost", { currency: referenceCurrency || "USD" })}
          hint={
            form.reference_cost !== "" && Number(exchangeRate) > 0
              ? t("inventory.referenceCostHint", {
                  price: (Number(form.reference_cost) * Number(exchangeRate)).toLocaleString(
                    undefined, { maximumFractionDigits: 2 },
                  ),
                })
              : t("inventory.referenceCostEmptyHint")
          }
        >
          <Input
            type="number" inputMode="decimal" min="0" step="0.0001"
            value={form.reference_cost} onChange={set("reference_cost")} className="w-40"
          />
        </Field>
        <label className="flex items-center gap-2 text-sm text-ink">
          <input type="checkbox" checked={form.track_batches} onChange={set("track_batches")} />
          {t("inventory.trackBatches")}
        </label>
        <label className="flex items-start gap-2 text-sm text-ink">
          <input
            type="checkbox"
            className="mt-1"
            checked={!form.is_stock_tracked}
            onChange={(e) =>
              setForm((f) => ({ ...f, is_stock_tracked: !e.target.checked }))
            }
          />
          <span>
            {t("inventory.noStock")}
            <span className="block text-xs text-muted">
              {t("inventory.noStockHint")}
            </span>
          </span>
        </label>
        {error && <p className="text-sm text-danger">{error}</p>}
        {editing && <PackEditor product={product} baseUnit={product?.unit_name} />}
      </div>
    </Drawer>
  );
}
