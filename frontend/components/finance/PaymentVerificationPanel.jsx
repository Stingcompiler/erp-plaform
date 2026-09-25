"use client";

import { useCallback, useEffect, useState } from "react";
import { BadgeCheck, ChevronDown, ShieldCheck } from "lucide-react";

import { sales } from "@/lib/api";
import { useI18n } from "../../app/providers/I18nProvider";
import { useToast } from "@/components/ui/Toast";
import { Badge, Button, Card } from "@/components/ui/kit";
import { SkeletonLines } from "@/components/ui/Skeleton";
import { channelLabel } from "@/lib/bankChannels";
import { errorText } from "@/lib/errors";
import { formatAmount } from "@/lib/money";
import { paymentMethodLabel } from "@/lib/labels";
import { useMoney } from "@/lib/useMoney";

const money = (v) => formatAmount(v);

/**
 * Customer payments nobody has confirmed yet. The API has always required a
 * second person for verification and an approver role above the company
 * threshold — but no screen ever listed what was waiting, so the control
 * never ran. Finance (or the sales manager) works this list down.
 *
 * The list starts folded to one line — how many are waiting and how much —
 * so the finance summary is the first thing on the page, not a long list.
 * A load failure says so (with a retry) instead of "nothing waiting".
 */
export default function PaymentVerificationPanel({ refreshKey }) {
  const { t, language } = useI18n();
  const { money: withCurrency } = useMoney();
  const toast = useToast();
  // null = loading, false = failed, [] = nothing waiting.
  const [rows, setRows] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [expanded, setExpanded] = useState(false);

  const load = useCallback(() => {
    setRows(null);
    sales.payments({ unverified: 1, page_size: 100 })
      .then((r) => setRows(r.data.results ?? r.data))
      .catch(() => setRows(false));
  }, []);
  useEffect(() => { load(); }, [load, refreshKey]);

  async function verify(payment) {
    setBusyId(payment.id);
    try {
      await sales.verifyPayment(payment.id);
      toast.success(t("finance.verifiedToast", { amount: money(payment.amount) }));
      load();
    } catch (err) {
      toast.error(errorText(err, t, "finance.verifyError"));
    } finally {
      setBusyId(null);
    }
  }

  const fmt = (v) => new Date(v).toLocaleString(language === "ar" ? "ar" : "en", { dateStyle: "medium", timeStyle: "short" });

  const waiting = Array.isArray(rows) ? rows : [];
  const waitingTotal = waiting.reduce((sum, p) => sum + Number(p.amount || 0), 0);

  return (
    <Card className="mb-5 p-4 sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 font-display text-lg font-semibold">
          <ShieldCheck size={18} className="text-accent" />{t("finance.verifyTitle")}
          {waiting.length > 0 && <Badge tone="warn">{waiting.length}</Badge>}
        </h2>
        {waiting.length > 0 && (
          <Button
            variant="outline"
            aria-expanded={expanded}
            aria-controls="payments-awaiting-list"
            onClick={() => setExpanded((open) => !open)}
          >
            {expanded ? t("states.hideList") : t("states.showList")}
            <ChevronDown size={15} className={`transition-transform ${expanded ? "rotate-180" : ""}`} />
          </Button>
        )}
      </div>
      <p className="mt-1 text-xs text-muted">{t("finance.verifyHint")}</p>
      {rows === null ? (
        <SkeletonLines lines={2} className="mt-2" />
      ) : rows === false ? (
        <div className="mt-3 flex flex-wrap items-center gap-3 text-sm">
          <p role="alert" className="text-danger">{t("states.verifyLoadError")}</p>
          <Button variant="outline" onClick={load}>{t("improvements.retry")}</Button>
        </div>
      ) : rows.length === 0 ? (
        <p className="mt-3 text-sm text-muted">{t("finance.verifyEmpty")}</p>
      ) : !expanded ? (
        <p className="mt-3 text-sm text-ink">
          {t("states.awaitingSummary", { count: waiting.length, amount: withCurrency(waitingTotal) })}
        </p>
      ) : (
        <div id="payments-awaiting-list" className="mt-3 divide-y divide-line">
          {rows.map((p) => (
            <div key={p.id} className="flex flex-wrap items-center gap-3 py-2.5 text-sm">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{p.customer_name || t("sales.walkIn")}</span>
                  <span className="tabular text-muted" dir="ltr">{p.invoice_number}</span>
                  <Badge tone={p.method === "cash" ? "muted" : "accent"}>
                    {paymentMethodLabel(t, p.method)}
                  </Badge>
                </div>
                <div className="mt-0.5 text-xs text-muted">
                  {p.recorded_by_name && t("finance.recordedByName", { name: p.recorded_by_name })}
                  {" · "}{fmt(p.recorded_at)}
                  {p.method === "bank_transfer" && (
                    <span dir="ltr">
                      {" · "}{p.bank_channel && p.bank_channel !== "bank" ? `${channelLabel(t, p.bank_channel)} · ` : ""}
                      {p.bank_account_name} · {p.sender_bank_name} · {p.transfer_reference || `#${p.reference_last4}`}
                    </span>
                  )}
                </div>
              </div>
              <div className="tabular text-base font-semibold">{money(p.amount)}</div>
              <Button variant="outline" onClick={() => verify(p)} disabled={busyId === p.id}>
                <BadgeCheck size={15} />{busyId === p.id ? t("finance.verifying") : t("finance.verify")}
              </Button>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
