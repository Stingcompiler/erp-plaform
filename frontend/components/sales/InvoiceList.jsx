"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { Ban, Download, Printer, HandCoins, Receipt } from "lucide-react";

import { sales } from "@/lib/api";
import { useAuth } from "../../app/providers/AuthProvider";
import { useI18n } from "../../app/providers/I18nProvider";
import DocumentDrawer from "@/components/print/DocumentDrawer";
import CollectPaymentDrawer from "@/components/sales/CollectPaymentDrawer";
import VoidDrawer from "@/components/finance/VoidDrawer";
import { Badge, Button, Card, Input } from "@/components/ui/kit";
import { SkeletonTableRows } from "@/components/ui/Skeleton";
import { EmptyTableRow } from "@/components/ui/EmptyState";

const money = (v) =>
  Number(v ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

// Invoice.status on the server: issued / partially_paid / paid / void.
const statusTone = { paid: "ok", partially_paid: "warn", issued: "danger", void: "muted" };
const OPEN_STATUSES = new Set(["issued", "partially_paid"]);

export default function InvoiceList({ refreshKey }) {
  const { t } = useI18n();
  const { can, canWrite } = useAuth();
  const canVoid = can("finance.approve");
  const canCollect = canWrite("sales");
  const [collecting, setCollecting] = useState(null);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [openId, setOpenId] = useState(null);
  const [voiding, setVoiding] = useState(null);
  // What the void hands back: money to refund vs. store credit kept as credit.
  const [voidPreview, setVoidPreview] = useState(null);
  useEffect(() => {
    setVoidPreview(null);
    if (!voiding) return undefined;
    let live = true;
    sales.voidPreview(voiding.id).then((r) => { if (live) setVoidPreview(r.data); }).catch(() => {});
    return () => { live = false; };
  }, [voiding]);
  const generation = useRef(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [count, setCount] = useState(0);
  const [next, setNext] = useState(false);
  const [error, setError] = useState(false);
  const [overdue, setOverdue] = useState(false);
  useEffect(() => { setOverdue(new URLSearchParams(window.location.search).get("overdue") === "1"); }, []);

  const load = useCallback(() => {
    const id = ++generation.current;
    setLoading(true); setError(false);
    sales
      .invoices({ page, search, overdue: overdue ? "1" : undefined })
      .then((r) => { if (id !== generation.current) return; setRows(r.data.results); setCount(r.data.count); setNext(Boolean(r.data.next)); })
      .catch(() => { if (id === generation.current) { setError(true); setRows([]); } })
      .finally(() => { if (id === generation.current) setLoading(false); });
  }, [page, search, overdue]);

  useEffect(() => {
    const timer = setTimeout(load, 200);
    return () => { clearTimeout(timer); generation.current += 1; };
  }, [load, refreshKey]);

  return (
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3">
        <Input className="max-w-xs" type="search" aria-label={t("common.search")} placeholder={t("common.search")} value={search} onChange={(e) => { setPage(1); setSearch(e.target.value); }} />
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={overdue} onChange={(e) => { setPage(1); setOverdue(e.target.checked); }} />{t("improvements.overdue")}</label>
        <Button
          variant="outline"
          onClick={() => window.open(sales.invoicesCsv({ search, overdue: overdue ? "1" : "" }), "_blank")}
        >
          <Download size={16} /> {t("common.export")}
        </Button>
      </div>
      {error && <div className="p-4"><p role="alert" className="text-danger">{t("improvements.loadError")}</p><Button onClick={load}>{t("improvements.retry")}</Button></div>}
      <div className="overflow-x-auto">
        <table className="stack-sm w-full text-sm">
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
              <SkeletonTableRows cols={5} />
            )}
            {!loading && !error && rows.length === 0 && (
              <EmptyTableRow
                cols={5}
                icon={Receipt}
                title={t("sales.emptyInvoicesTitle")}
                body={t("sales.emptyInvoicesBody")}
                filtered={Boolean(search || overdue)}
                onClearFilters={() => { setSearch(""); setOverdue(false); setPage(1); }}
              />
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
                    {canCollect && OPEN_STATUSES.has(inv.status) && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setCollecting(inv);
                        }}
                        title={t("debts.collect")}
                        aria-label={t("debts.collect")}
                        className="ms-1 rounded-control p-1.5 text-muted hover:bg-paper hover:text-accent"
                      >
                        <HandCoins size={15} />
                      </button>
                    )}
                    {canVoid && inv.status !== "void" && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setVoiding(inv);
                        }}
                        title={t("corrections.voidInvoice")}
                        aria-label={t("corrections.voidInvoice")}
                        className="ms-1 rounded-control p-1.5 text-muted hover:bg-paper hover:text-danger"
                      >
                        <Ban size={15} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between gap-3 border-t border-line p-3">
        <Button variant="outline" disabled={loading || page <= 1} onClick={() => setPage((p) => p-1)}>{t("improvements.previous")}</Button>
        <span className="text-sm text-muted">{t("improvements.page", {page,pages:Math.max(1,Math.ceil(count/50))})}</span>
        <Button variant="outline" disabled={loading || !next} onClick={() => setPage((p) => p+1)}>{t("improvements.next")}</Button>
      </div>
      <DocumentDrawer
        id={openId}
        open={Boolean(openId)}
        onClose={() => setOpenId(null)}
        fetcher={sales.invoiceDocument}
        title={t("sales.invoice")}
      />
      <CollectPaymentDrawer
        open={Boolean(collecting)}
        onClose={() => setCollecting(null)}
        invoice={collecting}
        customer={collecting ? { id: collecting.customer, name: collecting.customer_name } : null}
        onDone={load}
      />
      <VoidDrawer
        open={Boolean(voiding)}
        onClose={() => setVoiding(null)}
        onDone={load}
        title={t("corrections.voidInvoice")}
        summary={voiding ? `${voiding.number_display || voiding.number} · ${money(voiding.total)}` : ""}
        paidAmount={voidPreview ? voidPreview.refund : voiding?.amount_paid}
        creditAmount={voidPreview?.credit}
        submit={(body) => sales.voidInvoice(voiding.id, body)}
      />
    </Card>
  );
}
