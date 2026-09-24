"use client";

import { useCallback, useEffect, useState } from "react";
import { BadgeCheck, ShieldAlert } from "lucide-react";

import { sales } from "@/lib/api";
import { useI18n } from "../../app/providers/I18nProvider";
import { useToast } from "@/components/ui/Toast";
import { Badge, Button, Card, Input } from "@/components/ui/kit";
import { EmptyState } from "@/components/ui/EmptyState";
import { errorText } from "@/lib/errors";
import { SkeletonRows } from "@/components/ui/Skeleton";

const money = (v) =>
  v == null || v === "" ? "—"
    : Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/**
 * Sales an offline till kept although the price would have been refused at
 * the counter (below cost, or further below the list price than the
 * company's discount limit). The sale stands — it happened — and waits here
 * for an approver, or the branch's manager, to look and mark it reviewed.
 */
export default function PriceFlagReview() {
  const { t, language } = useI18n();
  const toast = useToast();
  const [rows, setRows] = useState(null);
  const [notes, setNotes] = useState({});
  const [busy, setBusy] = useState(null);
  const [loadError, setLoadError] = useState(null);

  // The toast API is a fresh object on every render of its provider, so the
  // load does not depend on it (a failed load would toast, re-render and
  // load again); a load error is shown in place instead.
  const load = useCallback(() => {
    setLoadError(null);
    sales.priceFlags()
      .then((r) => setRows(r.data.results || []))
      .catch((err) => { setRows([]); setLoadError(err); });
  }, []);
  useEffect(() => { load(); }, [load]);

  async function review(row) {
    setBusy(row.invoice);
    try {
      await sales.reviewPriceFlag(row.invoice, { note: notes[row.invoice] || "" });
      toast.success(t("priceFlags.reviewed"));
      setRows((current) => (current || []).filter((r) => r.invoice !== row.invoice));
    } catch (err) {
      toast.error(errorText(err, t, "priceFlags.reviewError"));
    } finally { setBusy(null); }
  }

  const fmt = (v) => (v ? new Date(v).toLocaleString(language === "ar" ? "ar" : "en", { dateStyle: "medium", timeStyle: "short" }) : "—");

  return (
    <Card>
      <div className="border-b border-line p-4">
        <h2 className="flex items-center gap-2 font-display text-lg font-semibold">
          <ShieldAlert size={18} className="text-warn" />{t("priceFlags.title")}
          {rows?.length > 0 && <Badge tone="warn">{rows.length}</Badge>}
        </h2>
        <p className="mt-1 text-sm text-muted">{t("priceFlags.subtitle")}</p>
      </div>
      {rows === null ? <SkeletonRows /> : loadError ? (
        <p className="p-6 text-center text-sm text-danger">{errorText(loadError, t, "priceFlags.loadError")}</p>
      ) : rows.length === 0 ? (
        <EmptyState icon={BadgeCheck} title={t("priceFlags.empty")} />
      ) : (
        <ul className="divide-y divide-line">
          {rows.map((row) => (
            <li key={row.invoice} className="flex flex-col gap-3 p-4 lg:flex-row lg:items-start lg:justify-between">
              <div className="min-w-0 space-y-1 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-ink">{row.invoice_number}</span>
                  {row.is_void && <Badge tone="muted">{t("priceFlags.void")}</Badge>}
                  {row.discount_percent && <Badge tone="warn">{t("priceFlags.percentOff", { percent: Number(row.discount_percent) })}</Badge>}
                  {row.limit && row.limit !== "None" && (
                    <span className="text-xs text-muted">{t("priceFlags.limit", { limit: Number(row.limit) })}</span>
                  )}
                </div>
                <div className="text-xs text-muted">
                  {t("priceFlags.date")}: {fmt(row.issued_at)}
                  {" · "}{t("priceFlags.cashier")}: {row.cashier || "—"}
                  {row.branch && <>{" · "}{t("priceFlags.branch")}: {row.branch}</>}
                </div>
                <ul className="space-y-0.5">
                  {row.breaches.map((b, i) => (
                    <li key={`${b.sku}-${b.rule}-${i}`} className="text-xs">
                      <span className="font-mono text-ink">{b.sku}</span>{" — "}
                      {b.list ? t("priceFlags.listVsSold", { list: money(b.list), sold: money(b.sold) }) : money(b.sold)}
                      {b.rule === "below_cost" && <span className="ms-1 text-danger">({t("priceFlags.belowCost")})</span>}
                      {b.rule === "discount" && b.percent && <span className="ms-1 text-warn">({t("priceFlags.percentOff", { percent: Number(b.percent) })})</span>}
                    </li>
                  ))}
                </ul>
              </div>
              <div className="flex shrink-0 flex-col gap-2 sm:flex-row sm:items-center">
                <Input
                  value={notes[row.invoice] || ""}
                  onChange={(e) => setNotes((n) => ({ ...n, [row.invoice]: e.target.value }))}
                  placeholder={t("priceFlags.note")}
                  aria-label={t("priceFlags.note")}
                  maxLength={255}
                  className="sm:w-56"
                />
                <Button variant="outline" onClick={() => review(row)} disabled={busy === row.invoice}>
                  <BadgeCheck size={15} />{t("priceFlags.markReviewed")}
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
