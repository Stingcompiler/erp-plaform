"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Archive, ArchiveRestore, Download, Lock, Pencil, Plus, Search } from "lucide-react";

import { inventory } from "@/lib/api";
import { offlineStore } from "@/lib/offlineStore";
import { useAuth } from "../../providers/AuthProvider";
import { useI18n } from "../../providers/I18nProvider";
import { useToast } from "@/components/ui/Toast";
import { Badge, Button, Card, Input, PageHeader } from "@/components/ui/kit";
import ProductForm from "@/components/inventory/ProductForm";
import StockDrawer from "@/components/inventory/StockDrawer";
import StockCountPanel from "@/components/inventory/StockCountPanel";

const PAGE_SIZE = 50;

export default function InventoryPage() {
  const { canRead, canWrite } = useAuth();
  const { t } = useI18n();
  const writable = canWrite("inventory");

  const [rows, setRows] = useState([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [lowOnly, setLowOnly] = useState(false);
  const [negativeOnly, setNegativeOnly] = useState(false);
  const [expiring, setExpiring] = useState([]);
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setLowOnly(params.get("low_stock") === "1");
    setNegativeOnly(params.get("negative") === "1");
  }, []);
  useEffect(() => {
    inventory.expiringBatches().then((r) => setExpiring(r.data.results || [])).catch(() => setExpiring([]));
  }, []);
  const [showArchived, setShowArchived] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const toast = useToast();

  const [categories, setCategories] = useState([]);
  const [warehouses, setWarehouses] = useState([]);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [stockFor, setStockFor] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const res = negativeOnly
        ? await inventory.negativeStock({ page })
        : lowOnly
        ? await inventory.lowStock({ page })
        : await inventory.products({
            page,
            search: search || undefined,
            archived: showArchived ? "1" : undefined,
          });
      setRows(res.data.results);
      setCount(res.data.count);
    } catch (err) {
      // Server unreachable: show the locally mirrored catalogue (filtered
      // client-side) rather than an empty error, so stock can still be
      // looked up and adjusted during an outage. A real server error (4xx)
      // still surfaces as one.
      if (err?.response) { setError(true); return; }
      try {
        const local = await offlineStore.getAll("products");
        const needle = (search || "").toLowerCase();
        const visible = local
          .filter((product) => (showArchived ? true : product.is_active !== false))
          .filter((product) => !needle || `${product.name} ${product.sku} ${product.barcode || ""}`.toLowerCase().includes(needle));
        setRows(visible.slice((page - 1) * 50, page * 50));
        setCount(visible.length);
      } catch {
        setError(true);
      }
    } finally {
      setLoading(false);
    }
  }, [page, search, lowOnly, negativeOnly, showArchived]);

  async function toggleArchive(product) {
    try {
      if (product.is_active === false) {
        await inventory.unarchiveProduct(product.id);
        toast.success(t("inventory.unarchived", { name: product.name }));
      } else {
        await inventory.archiveProduct(product.id);
        toast.success(t("inventory.archived", { name: product.name }));
      }
      load();
    } catch (err) {
      // The server explains *why* (e.g. a role that may edit but not archive),
      // and that reason is more useful than a generic failure message.
      toast.error(err?.response?.data?.detail || t("inventory.archiveFailed"));
    }
  }

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    inventory.categories().then((r) => setCategories(r.data.results)).catch(() => {});
    inventory.warehouses()
      .then((r) => setWarehouses(r.data.results))
      .catch(() => offlineStore.getAll("warehouses").then(setWarehouses).catch(() => {}));
  }, []);

  if (!canRead("inventory")) {
    return (
      <div className="mx-auto mt-16 max-w-md rounded-card border border-line bg-surface p-8 text-center">
        <Lock className="mx-auto text-muted" />
        <h1 className="mt-3 font-display text-xl font-semibold">{t("shell.noAccessTitle")}</h1>
        <p className="mt-1 text-muted">{t("inventory.noAccess")}</p>
      </div>
    );
  }

  const pages = Math.max(1, Math.ceil(count / PAGE_SIZE));

  const isLow = (p) =>
    Number(p.on_hand ?? 0) <= Number(p.reorder_level ?? 0);

  return (
    <div>
      <PageHeader
        title={t("inventory.title")}
        subtitle={t("inventory.productsCount", { count })}
        actions={
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => window.open(inventory.productsCsv({
              search: search || undefined,
              archived: showArchived ? "1" : undefined,
            }), "_blank")}>
              <Download size={16} /> {t("common.export")}
            </Button>
            {writable && (
              <Button
                onClick={() => {
                  setEditing(null);
                  setFormOpen(true);
                }}
              >
                <Plus size={16} /> {t("inventory.newProduct")}
              </Button>
            )}
          </div>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[220px]">
          <Search
            size={16}
            className="pointer-events-none absolute inset-y-0 start-3 my-auto text-muted"
          />
          <Input
            placeholder={t("inventory.searchPlaceholder")}
            value={search}
            onChange={(e) => {
              setPage(1);
              setSearch(e.target.value);
            }}
            disabled={lowOnly}
            className="ps-9"
          />
        </div>
        <label className="flex items-center gap-2 text-sm text-ink">
          <input
            type="checkbox"
            checked={lowOnly}
            onChange={(e) => {
              setPage(1);
              setLowOnly(e.target.checked);
            }}
          />
          {t("inventory.lowStockOnly")}
        </label>
        <label className="flex items-center gap-2 text-sm text-ink">
          <input
            type="checkbox"
            checked={negativeOnly}
            onChange={(e) => {
              setPage(1);
              setNegativeOnly(e.target.checked);
            }}
          />
          {t("inventory.negativeOnly")}
        </label>
        <label className="flex items-center gap-2 text-sm text-ink">
          <input
            type="checkbox"
            checked={showArchived}
            onChange={(e) => {
              setPage(1);
              setShowArchived(e.target.checked);
            }}
            disabled={lowOnly}
          />
          {t("inventory.showArchived")}
        </label>
      </div>

      <StockCountPanel warehouses={warehouses} canWrite={writable} />

      {expiring.length > 0 && (
        <Card className="mb-4 border-warn/40 p-4">
          <div className="mb-2 flex items-center gap-2 font-medium text-ink">
            <AlertTriangle size={16} className="text-warn" />
            {t("inventory.expiringTitle", { count: expiring.length })}
          </div>
          <ul className="grid gap-1 text-sm sm:grid-cols-2 lg:grid-cols-3">
            {expiring.slice(0, 9).map((row) => (
              <li key={row.batch} className={`flex items-center justify-between gap-2 rounded-control px-2 py-1 ${row.expired ? "bg-danger/10 text-danger" : "bg-warn/10 text-ink"}`}>
                <span className="truncate">{row.name} · {row.lot_number}</span>
                <span className="tabular shrink-0 text-xs">{row.remaining} · {row.expiry_date}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line text-start text-xs uppercase tracking-wide text-muted">
                <th className="px-4 py-3 text-start font-medium">{t("inventory.sku")}</th>
                <th className="px-4 py-3 text-start font-medium">{t("common.name")}</th>
                <th className="px-4 py-3 text-end font-medium">{t("inventory.onHand")}</th>
                <th className="px-4 py-3 text-end font-medium">{t("inventory.reorder")}</th>
                <th className="px-4 py-3 text-end font-medium">{t("common.price")}</th>
                <th className="px-4 py-3 text-end font-medium">{t("common.status")}</th>
                {writable && (
                  <th className="px-4 py-3 text-end font-medium">
                    {t("common.actions")}
                  </th>
                )}
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr>
                  <td colSpan={writable ? 7 : 6} className="px-4 py-8 text-center text-muted">
                    {t("common.loading")}
                  </td>
                </tr>
              )}
              {error && !loading && (
                <tr>
                  <td colSpan={writable ? 7 : 6} className="px-4 py-8 text-center text-muted">
                    {t("inventory.loadError")}
                  </td>
                </tr>
              )}
              {!loading && !error && rows.length === 0 && (
                <tr>
                  <td colSpan={writable ? 7 : 6} className="px-4 py-8 text-center text-muted">
                    {t("inventory.noProducts")} {writable ? t("inventory.createFirst") : ""}
                  </td>
                </tr>
              )}
              {!loading &&
                rows.map((p) => (
                  <tr
                    key={p.id}
                    onClick={() => setStockFor(p)}
                    className="cursor-pointer border-b border-line last:border-0 hover:bg-paper"
                  >
                    <td className="tabular px-4 py-3 text-ink">{p.sku}</td>
                    <td className="px-4 py-3 text-ink">
                      <span className="hover:underline">{p.name}</span>
                      {p.is_active === false && (
                        <span className="ms-2">
                          <Badge tone="muted">{t("inventory.archivedTag")}</Badge>
                        </span>
                      )}
                    </td>
                    <td className="tabular px-4 py-3 text-end text-ink">{p.on_hand}</td>
                    <td className="tabular px-4 py-3 text-end text-muted">{p.reorder_level}</td>
                    <td className="tabular px-4 py-3 text-end text-ink">{p.sale_price}</td>
                    <td className="px-4 py-3 text-end">
                      {isLow(p) ? <Badge tone="warn">{t("inventory.low")}</Badge> : <Badge tone="ok">{t("inventory.inStock")}</Badge>}
                    </td>
                    {/* A dedicated actions column: the edit affordance used to
                        be a small link beside the name, which people missed
                        because clicking the row opens stock instead. */}
                    {writable && (
                      <td className="px-4 py-3 text-end">
                        <div className="flex items-center justify-end gap-1">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setEditing(p);
                              setFormOpen(true);
                            }}
                            title={t("common.edit")}
                            aria-label={t("common.edit")}
                            className="rounded-control p-1.5 text-muted hover:bg-paper hover:text-ink"
                          >
                            <Pencil size={15} />
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              toggleArchive(p);
                            }}
                            title={
                              p.is_active === false
                                ? t("inventory.unarchive")
                                : t("inventory.archive")
                            }
                            aria-label={
                              p.is_active === false
                                ? t("inventory.unarchive")
                                : t("inventory.archive")
                            }
                            className="rounded-control p-1.5 text-muted hover:bg-paper hover:text-ink"
                          >
                            {p.is_active === false ? (
                              <ArchiveRestore size={15} />
                            ) : (
                              <Archive size={15} />
                            )}
                          </button>
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </Card>

      {pages > 1 && (
        <div className="mt-4 flex items-center justify-between text-sm text-muted">
          <span>{t("common.pageOf", { page, pages })}</span>
          <div className="flex gap-2">
            <Button variant="outline" disabled={page <= 1} onClick={() => setPage((n) => n - 1)}>
              {t("common.previous")}
            </Button>
            <Button variant="outline" disabled={page >= pages} onClick={() => setPage((n) => n + 1)}>
              {t("common.next")}
            </Button>
          </div>
        </div>
      )}

      <ProductForm
        open={formOpen}
        onClose={() => setFormOpen(false)}
        onSaved={load}
        product={editing}
        categories={categories}
      />
      <StockDrawer
        open={Boolean(stockFor)}
        onClose={() => setStockFor(null)}
        product={stockFor}
        warehouses={warehouses}
        canWrite={writable}
        onChanged={load}
      />
    </div>
  );
}
