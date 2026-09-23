"use client";

import { useCallback, useEffect, useState } from "react";
import { Plus } from "lucide-react";

import { returns } from "@/lib/api";
import { useI18n } from "../../app/providers/I18nProvider";
import { Button, Card } from "@/components/ui/kit";
import NewPurchaseReturnDrawer from "./NewPurchaseReturnDrawer";
import { SkeletonTableRows } from "@/components/ui/Skeleton";

/**
 * Goods sent back to suppliers. Read-only once recorded (append-only, Rule #9)
 * — there is no disposition step because the stock has already left.
 */
export default function PurchaseReturnList({ writable }) {
  const { t } = useI18n();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [newOpen, setNewOpen] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    returns
      .purchaseReturns({ page: 1 })
      .then((r) => setRows(r.data.results || r.data))
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div>
      {writable && (
        <div className="mb-4 flex justify-end">
          <Button onClick={() => setNewOpen(true)}>
            <Plus size={16} /> {t("returns.newPurchaseReturn")}
          </Button>
        </div>
      )}

      <Card>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line text-xs uppercase tracking-wide text-muted">
                <th className="px-4 py-3 text-start font-medium">{t("returns.return")}</th>
                <th className="px-4 py-3 text-start font-medium">
                  {t("purchasing.supplier")}
                </th>
                <th className="px-4 py-3 text-start font-medium">{t("returns.reason")}</th>
                <th className="px-4 py-3 text-end font-medium">{t("returns.lines")}</th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <SkeletonTableRows cols={4} />
              )}
              {!loading && rows.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-8 text-center text-muted">
                    {t("returns.noPurchaseReturns")}
                  </td>
                </tr>
              )}
              {!loading &&
                rows.map((r) => (
                  <tr key={r.id} className="border-b border-line last:border-0">
                    <td className="tabular px-4 py-3 text-ink">#{r.id}</td>
                    <td className="px-4 py-3 text-ink">
                      {r.supplier_name || `#${r.supplier}`}
                    </td>
                    <td className="px-4 py-3 text-muted">{r.reason || "—"}</td>
                    <td className="tabular px-4 py-3 text-end text-ink">
                      {r.lines?.length ?? 0}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </Card>

      <NewPurchaseReturnDrawer
        open={newOpen}
        onClose={() => setNewOpen(false)}
        onCreated={load}
      />
    </div>
  );
}
