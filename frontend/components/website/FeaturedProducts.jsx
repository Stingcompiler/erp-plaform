"use client";

import { useCallback, useEffect, useState } from "react";
import { Pencil, Plus, Search, Trash2 } from "lucide-react";

import { inventory, website } from "@/lib/api";
import { useI18n } from "../../app/providers/I18nProvider";
import Drawer from "@/components/ui/Drawer";
import { Button, Card, Field, Input } from "@/components/ui/kit";

function FeaturedForm({ open, onClose, onSaved, websiteId, item }) {
  const { t } = useI18n();
  const editing = Boolean(item);
  const [product, setProduct] = useState(null); // {id, name}
  const [caption, setCaption] = useState("");
  const [order, setOrder] = useState(0);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (item) {
      setProduct({ id: item.product, name: item.product_name || `#${item.product}` });
      setCaption(item.caption || "");
      setOrder(item.order ?? 0);
    } else {
      setProduct(null);
      setCaption("");
      setOrder(0);
    }
    setQuery("");
    setResults([]);
    setError("");
  }, [item, open]);

  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      return undefined;
    }
    const timer = setTimeout(() => {
      inventory
        .products({ search: query })
        .then((r) => setResults(r.data.results.slice(0, 6)))
        .catch(() => setResults([]));
    }, 250);
    return () => clearTimeout(timer);
  }, [query]);

  async function save() {
    setError("");
    if (!product) return setError(t("website.chooseProductErr"));
    setSaving(true);
    try {
      const body = { product: product.id, caption, order: Number(order) || 0 };
      if (editing) {
        await website.updateFeatured(item.id, body);
      } else {
        await website.createFeatured({ ...body, website: websiteId });
      }
      onSaved();
      onClose();
    } catch (err) {
      const data = err?.response?.data;
      setError(
        typeof data === "object" && data ? Object.values(data).flat().join(" ") : t("website.saveError")
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={editing ? t("website.editFeatured") : t("website.featureProduct")}
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button onClick={save} disabled={saving || !product}>
            {saving ? t("common.saving") : editing ? t("common.save") : t("common.add")}
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        <div>
          <span className="mb-1 block text-sm font-medium text-ink">{t("website.featuredProduct")}</span>
          {product ? (
            <div className="flex items-center justify-between rounded-card border border-line px-3 py-2 text-sm">
              <span className="text-ink">{product.name}</span>
              <button className="text-muted hover:text-danger" onClick={() => setProduct(null)}>
                {t("website.change")}
              </button>
            </div>
          ) : (
            <div className="relative">
              <Search size={16} className="pointer-events-none absolute inset-y-0 start-3 my-auto text-muted" />
              <Input
                placeholder={t("website.searchProduct")}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="ps-9"
              />
              {results.length > 0 && (
                <div className="absolute z-10 mt-1 w-full overflow-hidden rounded-card border border-line bg-surface shadow-card">
                  {results.map((p) => (
                    <button
                      key={p.id}
                      onClick={() => {
                        setProduct({ id: p.id, name: p.name });
                        setQuery("");
                        setResults([]);
                      }}
                      className="flex w-full items-center justify-between px-3 py-2 text-start text-sm hover:bg-paper"
                    >
                      <span className="text-ink">{p.name}</span>
                      <span className="tabular text-muted">{p.sku}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
        <Field label={t("website.caption")}>
          <Input value={caption} onChange={(e) => setCaption(e.target.value)} placeholder={t("common.optional")} />
        </Field>
        <Field label={t("website.order")}>
          <Input type="number" value={order} onChange={(e) => setOrder(e.target.value)} />
        </Field>
        {error && <p className="text-sm text-danger">{error}</p>}
      </div>
    </Drawer>
  );
}

export default function FeaturedProducts({ websiteId, writable }) {
  const { t } = useI18n();
  const [rows, setRows] = useState([]);
  const [productsById, setProductsById] = useState({});
  const [loading, setLoading] = useState(true);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    website
      .featured()
      .then((r) => setRows(r.data.results || r.data))
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
    // Best-effort product-name lookup for display (first page).
    inventory
      .products({ page: 1 })
      .then((r) => {
        const map = {};
        (r.data.results || []).forEach((p) => {
          map[p.id] = p.name;
        });
        setProductsById(map);
      })
      .catch(() => {});
  }, [load]);

  async function remove(item) {
    if (!window.confirm(t("website.removeFeaturedConfirm"))) return;
    await website.deleteFeatured(item.id).catch(() => {});
    load();
  }

  const name = (item) => productsById[item.product] || `#${item.product}`;

  return (
    <Card className="mt-6 p-6">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="font-display text-sm font-semibold uppercase tracking-wide text-muted">
          {t("website.featuredProducts")}
        </h2>
        {writable && websiteId && (
          <Button
            onClick={() => {
              setEditing(null);
              setFormOpen(true);
            }}
          >
            <Plus size={16} /> {t("website.featureProductBtn")}
          </Button>
        )}
      </div>

      {loading ? (
        <p className="text-sm text-muted">{t("common.loading")}</p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-muted">{t("website.featuredEmptyHint")}</p>
      ) : (
        <div className="divide-y divide-line">
          {rows.map((item) => (
            <div key={item.id} className="flex items-center gap-3 py-3">
              <span className="tabular w-8 text-center text-xs text-muted">{item.order}</span>
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm text-ink">{name(item)}</div>
                {item.caption && (
                  <div className="truncate text-xs text-muted">{item.caption}</div>
                )}
              </div>
              {writable && (
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => {
                      setEditing({ ...item, product_name: name(item) });
                      setFormOpen(true);
                    }}
                    className="rounded p-1.5 text-muted hover:bg-paper hover:text-ink"
                    aria-label={t("common.edit")}
                  >
                    <Pencil size={15} />
                  </button>
                  <button
                    onClick={() => remove(item)}
                    className="rounded p-1.5 text-muted hover:bg-paper hover:text-danger"
                    aria-label={t("sales.remove")}
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <FeaturedForm
        open={formOpen}
        onClose={() => setFormOpen(false)}
        onSaved={load}
        websiteId={websiteId}
        item={editing}
      />
    </Card>
  );
}
