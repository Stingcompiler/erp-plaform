"use client";

import { useCallback, useEffect, useState } from "react";
import { FileText } from "lucide-react";

import { returns } from "@/lib/api";
import { useI18n } from "../../app/providers/I18nProvider";
import DocumentDrawer from "@/components/print/DocumentDrawer";
import { Badge, Card } from "@/components/ui/kit";

const money = (v) =>
  Number(v ?? 0).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

/**
 * Credit and debit notes with their printable document.
 *
 * Rule #6 makes the system issue one of these for every return, and it always
 * did — but nothing surfaced them, so the document proving a customer's money
 * was credited back existed only in the database. This is the screen that hands
 * it over.
 */
export default function NotesList({ kind }) {
  const { t } = useI18n();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [openId, setOpenId] = useState(null);

  const isCredit = kind === "credit";
  const list = isCredit ? returns.creditNotes : returns.debitNotes;
  const fetcher = isCredit
    ? returns.creditNoteDocument
    : returns.debitNoteDocument;
  const prefix = isCredit ? "CN" : "DN";

  const load = useCallback(() => {
    setLoading(true);
    list({ page: 1 })
      .then((r) => setRows(r.data.results || r.data))
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, [list]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <Card>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-line text-xs uppercase tracking-wide text-muted">
              <th className="px-4 py-3 text-start font-medium">{t("doc.number")}</th>
              <th className="px-4 py-3 text-start font-medium">
                {isCredit ? t("doc.billTo") : t("doc.supplier")}
              </th>
              <th className="px-4 py-3 text-start font-medium">{t("doc.reason")}</th>
              <th className="px-4 py-3 text-end font-medium">{t("doc.amount")}</th>
              <th className="px-4 py-3" />
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
                  {t("returns.noNotes")}
                </td>
              </tr>
            )}
            {!loading &&
              rows.map((n) => (
                <tr key={n.id} className="border-b border-line last:border-0">
                  <td className="tabular px-4 py-3 text-ink">
                    {prefix}-{String(n.id).padStart(6, "0")}
                  </td>
                  <td className="px-4 py-3 text-ink">
                    {n.customer_name || n.supplier_name || "—"}
                  </td>
                  <td className="px-4 py-3 text-muted">{n.reason || "—"}</td>
                  <td className="tabular px-4 py-3 text-end text-ink">
                    {money(n.amount)}
                    {n.is_void && (
                      <span className="ms-2">
                        <Badge tone="muted">{t("doc.void")}</Badge>
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-end">
                    <button
                      onClick={() => setOpenId(n.id)}
                      className="inline-flex items-center gap-1.5 text-sm text-accent hover:underline"
                    >
                      <FileText size={14} /> {t("doc.document")}
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
        fetcher={fetcher}
        title={isCredit ? t("doc.titleCreditNote") : t("doc.titleDebitNote")}
      />
    </Card>
  );
}
