"use client";

import { useCallback, useEffect, useState } from "react";
import { Ban, FileText, HandCoins } from "lucide-react";

import { returns } from "@/lib/api";
import { useAuth } from "../../app/providers/AuthProvider";
import { useI18n } from "../../app/providers/I18nProvider";
import DocumentDrawer from "@/components/print/DocumentDrawer";
import RefundDrawer from "@/components/finance/RefundDrawer";
import VoidDrawer from "@/components/finance/VoidDrawer";
import { Badge, Card } from "@/components/ui/kit";
import { SkeletonTableRows } from "@/components/ui/Skeleton";

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
  const { can, canWrite } = useAuth();
  const canVoid = can("finance.approve");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [openId, setOpenId] = useState(null);
  const [refunding, setRefunding] = useState(null);
  const [voiding, setVoiding] = useState(null);

  const isCredit = kind === "credit";
  const canRefund = isCredit && canWrite("sales_returns");
  const voidNote = isCredit ? returns.voidCreditNote : returns.voidDebitNote;
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
        <table className="stack-sm w-full text-sm">
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
              <SkeletonTableRows cols={5} />
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
                    {n.number_display || `${prefix}-${String(n.id).padStart(6, "0")}`}
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
                    <span className="inline-flex items-center gap-3">
                      {canRefund && !n.is_void && Number(n.remaining_refundable) > 0 && (
                        <button
                          onClick={() => setRefunding(n)}
                          className="inline-flex items-center gap-1.5 text-sm text-accent hover:underline"
                        >
                          <HandCoins size={14} /> {t("corrections.refund")}
                        </button>
                      )}
                      <button
                        onClick={() => setOpenId(n.id)}
                        className="inline-flex items-center gap-1.5 text-sm text-accent hover:underline"
                      >
                        <FileText size={14} /> {t("doc.document")}
                      </button>
                      {canVoid && !n.is_void && (
                        <button
                          onClick={() => setVoiding(n)}
                          title={t("corrections.voidNote")}
                          aria-label={t("corrections.voidNote")}
                          className="rounded-control p-1 text-muted hover:text-danger"
                        >
                          <Ban size={14} />
                        </button>
                      )}
                    </span>
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
      <RefundDrawer
        note={refunding}
        open={Boolean(refunding)}
        onClose={() => setRefunding(null)}
        onDone={load}
      />
      <VoidDrawer
        open={Boolean(voiding)}
        onClose={() => setVoiding(null)}
        onDone={load}
        title={t("corrections.voidNote")}
        summary={voiding ? `${voiding.number_display} · ${money(voiding.amount)}` : ""}
        submit={(body) => voidNote(voiding.id, body)}
      />
    </Card>
  );
}
