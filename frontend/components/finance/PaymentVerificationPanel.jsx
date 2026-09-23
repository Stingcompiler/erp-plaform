"use client";

import { useCallback, useEffect, useState } from "react";
import { BadgeCheck, ShieldCheck } from "lucide-react";

import { sales } from "@/lib/api";
import { useI18n } from "../../app/providers/I18nProvider";
import { useToast } from "@/components/ui/Toast";
import { Badge, Button, Card } from "@/components/ui/kit";
import { channelLabel } from "@/lib/bankChannels";
import { errorText } from "@/lib/errors";

const money = (v) =>
  Number(v ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/**
 * Customer payments nobody has confirmed yet. The API has always required a
 * second person for verification and an approver role above the company
 * threshold — but no screen ever listed what was waiting, so the control
 * never ran. Finance (or the sales manager) works this list down.
 */
export default function PaymentVerificationPanel({ refreshKey }) {
  const { t, language } = useI18n();
  const toast = useToast();
  const [rows, setRows] = useState(null);
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(() => {
    sales.payments({ unverified: 1, page_size: 100 })
      .then((r) => setRows(r.data.results ?? r.data))
      .catch(() => setRows([]));
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

  return (
    <Card className="mb-5 p-4 sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 font-display text-lg font-semibold">
          <ShieldCheck size={18} className="text-accent" />{t("finance.verifyTitle")}
          {rows?.length > 0 && <Badge tone="warn">{rows.length}</Badge>}
        </h2>
        <p className="text-xs text-muted">{t("finance.verifyHint")}</p>
      </div>
      {rows === null ? null : rows.length === 0 ? (
        <p className="mt-4 text-sm text-muted">{t("finance.verifyEmpty")}</p>
      ) : (
        <div className="mt-3 divide-y divide-line">
          {rows.map((p) => (
            <div key={p.id} className="flex flex-wrap items-center gap-3 py-2.5 text-sm">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{p.customer_name || t("sales.walkIn")}</span>
                  <span className="tabular text-muted" dir="ltr">{p.invoice_number}</span>
                  <Badge tone={p.method === "cash" ? "muted" : "accent"}>
                    {t(p.method === "cash" ? "common.cash" : "common.bankTransfer")}
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
