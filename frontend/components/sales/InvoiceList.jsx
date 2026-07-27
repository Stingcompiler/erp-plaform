"use client";

import { useCallback, useEffect, useState } from "react";

import { Download, Printer } from "lucide-react";

import { sales } from "@/lib/api";
import { useI18n } from "../../app/providers/I18nProvider";
import DocumentDrawer from "@/components/print/DocumentDrawer";
import { Badge, Button, Card } from "@/components/ui/kit";

const money = (v) =>
  Number(v ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const statusTone = { paid: "ok", partial: "warn", unpaid: "danger", void: "muted" };

export default function InvoiceList({ refreshKey }) {
  const { t } = useI18n();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [openId, setOpenId] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    sales
      .invoices({ page: 1 })
      .then((r) => setRows(r.data.results))
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  return (
    <Card>
      <div className="flex justify-end border-b border-line px-4 py-3">
        <Button
          variant="outline"
          onClick={() => window.open(sales.invoicesCsv(), "_blank")}
        >
          <Download size={16} /> {t("common.export")}
        </Button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-line text-xs uppercase tracking-wide text-muted">
              <th className="px-4 py-3 text-start font-medium">{t("sales.invoice")}</th>
              <th className="px-4 py-3 text-start font-medium">{t("sales.customer")}</th>
              <th className="px-4 py-3 text-end font-medium">{t("common.total")}</th>
              <th className="px-4 py-3 text-end font-medium">{t("common.status")}</th>
              <th className="px-4 py-3 text-end font-medium">{t("common.actions")}</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-muted">
                  {t("common.loading")}
                </td>
              </tr>
            )}
            {!loading && rows.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-muted">
                  {t("sales.noInvoices")}
                </td>
              </tr>
            )}
            {!loading &&
              rows.map((inv) => (
                <tr
                  key={inv.id}
                  onClick={() => setOpenId(inv.id)}
                  className="cursor-pointer border-b border-line last:border-0 hover:bg-paper"
                >
                  <td className="tabular px-4 py-3 text-ink">
                    {inv.number_display || inv.number}
                  </td>
                  <td className="px-4 py-3 text-ink">{inv.customer_name || t("sales.walkIn")}</td>
                  <td className="tabular px-4 py-3 text-end text-ink">{money(inv.total)}</td>
                  <td className="px-4 py-3 text-end">
                    <Badge tone={statusTone[inv.status] || "muted"}>{inv.status}</Badge>
                  </td>
                  {/* Opening the row already showed the document, but nothing
                      said so — an explicit action is what people look for. */}
                  <td className="px-4 py-3 text-end">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setOpenId(inv.id);
                      }}
                      title={t("doc.print")}
                      aria-label={t("doc.print")}
                      className="rounded-control p-1.5 text-muted hover:bg-paper hover:text-ink"
                    >
                      <Printer size={15} />
                    </button>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
      <DocumentDrawer
        id={openId}
        open={Boolean(openId)}
        onClose={() => setOpenId(null)}
        fetcher={sales.invoiceDocument}
        title={t("sales.invoice")}
      />
    </Card>
  );
}
