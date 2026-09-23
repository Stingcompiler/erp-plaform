"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Lock, Printer, Search } from "lucide-react";

import { inventory } from "@/lib/api";
import { useAuth } from "../../providers/AuthProvider";
import { useI18n } from "../../providers/I18nProvider";
import { ean13Svg } from "@/lib/ean13";
import { Button, Card, Input, PageHeader } from "@/components/ui/kit";
import { SkeletonRows } from "@/components/ui/Skeleton";

const money = (v, lang) =>
  Number(v ?? 0).toLocaleString(lang === "ar" ? "ar" : "en", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

// One printable label: name, price and the scannable EAN-13.
function Label({ product, lang }) {
  const svg = ean13Svg(product.barcode, { moduleWidth: 2, height: 48 });
  return (
    <div className="label break-inside-avoid rounded border border-line p-2 text-center">
      <div className="truncate text-xs font-medium text-ink">{product.name}</div>
      <div
        className="my-1 flex justify-center text-ink"
        dangerouslySetInnerHTML={{ __html: svg }}
      />
      <div className="tabular text-xs text-ink">{money(product.sale_price, lang)}</div>
    </div>
  );
}

export default function LabelsPage() {
  const { canWrite } = useAuth();
  const { t, language } = useI18n();
  // Printing labels is an inventory-management task.
  const allowed = canWrite("inventory");

  const [products, setProducts] = useState([]);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(() => new Set());
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    inventory
      .products({ page: 1 })
      .then((r) => setProducts((r.data.results || r.data).filter((p) => p.barcode)))
      .catch(() => setProducts([]))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (allowed) load();
    else setLoading(false);
  }, [allowed, load]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q
      ? products.filter(
          (p) =>
            p.name.toLowerCase().includes(q) ||
            p.sku.toLowerCase().includes(q) ||
            (p.barcode || "").includes(q)
        )
      : products;
  }, [products, query]);

  const toggle = (id) =>
    setSelected((s) => {
      const next = new Set(s);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const chosen = products.filter((p) => selected.has(p.id));

  if (!allowed) {
    return (
      <div className="mx-auto mt-16 max-w-md rounded-card border border-line bg-surface p-8 text-center">
        <Lock className="mx-auto text-muted" />
        <h1 className="mt-3 font-display text-xl font-semibold">{t("shell.noAccessTitle")}</h1>
        <p className="mt-1 text-muted">{t("inventory.noAccess")}</p>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title={t("inventory.labels")}
        subtitle={t("inventory.labelsHint")}
        actions={
          <Button onClick={() => window.print()} disabled={chosen.length === 0}>
            <Printer size={16} /> {t("inventory.printLabel")} ({chosen.length})
          </Button>
        }
      />

      {/* Picker — hidden when printing */}
      <div className="print:hidden">
        <div className="relative mb-3 max-w-sm">
          <Search size={15} className="pointer-events-none absolute inset-y-0 start-3 my-auto text-muted" />
          <Input
            className="ps-9"
            placeholder={t("common.search")}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>

        {loading && <SkeletonRows />}
        {!loading && products.length === 0 && (
          <Card className="p-8 text-center text-muted">{t("inventory.noBarcodeProducts")}</Card>
        )}
        {!loading && visible.length > 0 && (
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {visible.map((p) => (
              <label
                key={p.id}
                className={`flex cursor-pointer items-center gap-3 rounded-card border p-3 text-sm ${
                  selected.has(p.id) ? "border-accent bg-accent/5" : "border-line bg-surface"
                }`}
              >
                <input
                  type="checkbox"
                  checked={selected.has(p.id)}
                  onChange={() => toggle(p.id)}
                />
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium text-ink">{p.name}</div>
                  <div className="tabular text-xs text-muted">{p.barcode}</div>
                </div>
              </label>
            ))}
          </div>
        )}
      </div>

      {/* Print sheet — only this shows when printing */}
      {chosen.length > 0 && (
        <div className="mt-6 hidden print:mt-0 print:block">
          <div className="grid grid-cols-3 gap-2">
            {chosen.map((p) => (
              <Label key={p.id} product={p} lang={language} />
            ))}
          </div>
        </div>
      )}

      <style jsx global>{`
        @media print {
          body * {
            visibility: hidden;
          }
          .label,
          .label * {
            visibility: visible;
          }
          .label {
            page-break-inside: avoid;
          }
        }
      `}</style>
    </div>
  );
}
