"use client";

import { useCallback, useEffect, useRef, useState } from "react";
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
function Label({ item, lang }) {
  const svg = ean13Svg(item.barcode, { moduleWidth: 2, height: 48 });
  return (
    <div className="label break-inside-avoid rounded border border-line p-2 text-center">
      <div className="truncate text-xs font-medium text-ink">{item.name}</div>
      <div
        className="my-1 flex justify-center text-ink"
        dangerouslySetInnerHTML={{ __html: svg }}
      />
      <div className="tabular text-xs text-ink">{money(item.price, lang)}</div>
    </div>
  );
}

// Every printable code a product carries: its own barcode and each active
// pack's (a carton label rings up the whole carton).
function labelItems(product) {
  const items = [];
  if (product.barcode) {
    items.push({
      key: `p-${product.id}`, name: product.name, sku: product.sku,
      barcode: product.barcode, price: product.sale_price,
    });
  }
  for (const pack of product.packs || []) {
    if (pack.is_active === false || !pack.barcode) continue;
    items.push({
      key: `k-${pack.id}`, name: `${product.name} — ${pack.name}`, sku: product.sku,
      barcode: pack.barcode, price: pack.effective_price,
    });
  }
  return items;
}

export default function LabelsPage() {
  const { canWrite } = useAuth();
  const { t, language } = useI18n();
  // Printing labels is an inventory-management task.
  const allowed = canWrite("inventory");

  const [items, setItems] = useState([]);
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  // Chosen labels by key, kept across searches so a sheet can mix products
  // found by different searches.
  const [selected, setSelected] = useState(() => new Map());
  const [loading, setLoading] = useState(true);
  const request = useRef(0);

  // The server searches and pages (the catalogue can hold thousands of
  // products; only the first page used to be reachable here).
  const load = useCallback((search, pageNo) => {
    const ticket = ++request.current;
    setLoading(true);
    inventory
      .products({ page: pageNo, has_barcode: 1, ...(search ? { search } : {}) })
      .then((r) => {
        if (ticket !== request.current) return;
        const rows = (r.data.results || r.data).flatMap(labelItems);
        setItems((prev) => (pageNo === 1 ? rows : [...prev, ...rows]));
        setHasMore(Boolean(r.data.next));
        setPage(pageNo);
      })
      .catch(() => {
        if (ticket !== request.current) return;
        if (pageNo === 1) setItems([]);
        setHasMore(false);
      })
      .finally(() => {
        if (ticket === request.current) setLoading(false);
      });
  }, []);

  useEffect(() => {
    if (!allowed) {
      setLoading(false);
      return undefined;
    }
    const timer = setTimeout(() => load(query.trim(), 1), 300);
    return () => clearTimeout(timer);
  }, [allowed, load, query]);

  const toggle = (item) =>
    setSelected((s) => {
      const next = new Map(s);
      next.has(item.key) ? next.delete(item.key) : next.set(item.key, item);
      return next;
    });

  const chosen = [...selected.values()];

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

        {loading && items.length === 0 && <SkeletonRows />}
        {!loading && items.length === 0 && (
          <Card className="p-8 text-center text-muted">{t("inventory.noBarcodeProducts")}</Card>
        )}
        {items.length > 0 && (
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {items.map((item) => (
              <label
                key={item.key}
                className={`flex cursor-pointer items-center gap-3 rounded-card border p-3 text-sm ${
                  selected.has(item.key) ? "border-accent bg-accent/5" : "border-line bg-surface"
                }`}
              >
                <input
                  type="checkbox"
                  checked={selected.has(item.key)}
                  onChange={() => toggle(item)}
                />
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium text-ink">{item.name}</div>
                  <div className="tabular text-xs text-muted">{item.barcode}</div>
                </div>
              </label>
            ))}
          </div>
        )}
        {hasMore && (
          <div className="mt-3 text-center">
            <Button variant="outline" disabled={loading} onClick={() => load(query.trim(), page + 1)}>
              {t("inventory.loadMoreLabels")}
            </Button>
          </div>
        )}
      </div>

      {/* Print sheet — only this shows when printing */}
      {chosen.length > 0 && (
        <div className="mt-6 hidden print:mt-0 print:block">
          <div className="grid grid-cols-3 gap-2">
            {chosen.map((item) => (
              <Label key={item.key} item={item} lang={language} />
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
