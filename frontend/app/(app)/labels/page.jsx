"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Lock, Printer, Search } from "lucide-react";

import { inventory } from "@/lib/api";
import { useAuth } from "../../providers/AuthProvider";
import { useI18n } from "../../providers/I18nProvider";
import { ean13Svg, isValidEan13 } from "@/lib/ean13";
import { code128Svg } from "@/lib/code128";
import { Button, Card, Input, PageHeader, Select } from "@/components/ui/kit";
import PrintSheet from "@/components/print/PrintSheet";
import { SkeletonRows } from "@/components/ui/Skeleton";

const money = (v, lang) =>
  Number(v ?? 0).toLocaleString(lang === "ar" ? "ar" : "en", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

// Real label stock, in millimetres. `bars` is the box the EAN-13 bars are
// drawn into: wide enough for a module of at least 0.29 mm (88 % of the
// standard size, which every till scanner reads) with the quiet zones.
const LABEL_FORMATS = {
  "label-a4": { w: 70, h: 37, bars: [44, 17], name: 9, price: 11 },
  "label-40x30": { w: 40, h: 30, bars: [34, 13], name: 7.5, price: 9 },
  "label-50x25": { w: 50, h: 25, bars: [40, 10], name: 7.5, price: 9 },
};
const LABEL_KEY = "print.labelFormat";

// A valid EAN-13 prints as one; any other code (typed by hand, a supplier's
// own, a 13-digit number with a wrong check digit) as Code 128, which every
// till scanner also reads. Before, those printed with no bars at all.
function barsSvg(code) {
  const s = String(code || "").trim();
  return isValidEan13(s)
    ? ean13Svg(s, { moduleWidth: 2, height: 60, showText: false })
    : code128Svg(s, { moduleWidth: 2, height: 60 });
}

// One printable label: name, the scannable code with its digits, price.
// Bars are drawn without text and stretched into the box (every module scales
// alike, so it still scans); the digits are real text underneath.
function Label({ item, lang, format }) {
  const f = LABEL_FORMATS[format];
  const svg = barsSvg(item.barcode).replace("<svg ", '<svg preserveAspectRatio="none" ');
  return (
    <div className="label" style={{ width: `${f.w}mm`, height: `${f.h}mm` }}>
      <div className="label-name" style={{ fontSize: `${f.name}pt` }}>{item.name}</div>
      <div
        className="label-bars"
        style={{ width: `${f.bars[0]}mm`, height: `${f.bars[1]}mm` }}
        dangerouslySetInnerHTML={{ __html: svg }}
      />
      <div className="label-digits" dir="ltr">{item.barcode}</div>
      <div className="label-price" style={{ fontSize: `${f.price}pt` }}>{money(item.price, lang)}</div>
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
  const [copies, setCopies] = useState(1);
  const [format, setFormat] = useState("label-a4");
  const request = useRef(0);

  // The label stock is a property of this shop's printer, so the browser
  // remembers it.
  useEffect(() => {
    try {
      const saved = localStorage.getItem(LABEL_KEY);
      if (LABEL_FORMATS[saved]) setFormat(saved);
    } catch { /* private mode */ }
  }, []);
  function chooseFormat(next) {
    setFormat(next);
    try { localStorage.setItem(LABEL_KEY, next); } catch { /* per-device convenience only */ }
  }

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
  const sheet = chosen.flatMap((item) =>
    Array.from({ length: copies }, (_, n) => ({ ...item, copyKey: `${item.key}-${n}` })));

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
          <div className="flex flex-wrap items-center gap-2">
            <div className="w-44">
              <Select value={format} onChange={(e) => chooseFormat(e.target.value)} aria-label={t("inventory.labelFormat")}>
                {Object.keys(LABEL_FORMATS).map((k) => (
                  <option key={k} value={k}>{t(`inventory.${k.replace("-", "_")}`)}</option>
                ))}
              </Select>
            </div>
            <div className="w-24">
              <Input
                type="number" min={1} max={100} value={copies}
                aria-label={t("inventory.labelCopies")} title={t("inventory.labelCopies")}
                onChange={(e) => setCopies(Math.min(100, Math.max(1, Number(e.target.value) || 1)))}
              />
            </div>
            <Button onClick={() => window.print()} disabled={chosen.length === 0}>
              <Printer size={16} /> {t("inventory.printLabel")} ({sheet.length})
            </Button>
          </div>
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
      {sheet.length > 0 && (
        <PrintSheet paper={format}>
          <div className={format === "label-a4" ? "label-grid" : ""}>
            {sheet.map((item) => (
              <Label key={item.copyKey} item={item} lang={language} format={format} />
            ))}
          </div>
        </PrintSheet>
      )}

      <style jsx global>{`
        .label-grid {
          display: grid;
          grid-template-columns: repeat(3, 70mm);
          grid-auto-rows: 37mm;
        }
        .label {
          box-sizing: border-box;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 0.4mm;
          overflow: hidden;
          padding: 1.5mm 2mm;
          color: #000;
          text-align: center;
          break-inside: avoid;
          page-break-inside: avoid;
        }
        /* On a roll every label is its own page. */
        .print-sheet > div:not(.label-grid) > .label:not(:last-child) {
          page-break-after: always;
          break-after: page;
        }
        .label-name {
          max-width: 100%;
          overflow: hidden;
          white-space: nowrap;
          text-overflow: ellipsis;
          font-weight: 600;
          line-height: 1.2;
        }
        .label-bars svg {
          display: block;
          width: 100%;
          height: 100%;
          color: #000;
        }
        .label-digits {
          font-family: ui-monospace, monospace;
          font-size: 7pt;
          letter-spacing: 0.6mm;
          line-height: 1;
        }
        .label-price {
          font-weight: 700;
          line-height: 1.1;
        }
      `}</style>
    </div>
  );
}
