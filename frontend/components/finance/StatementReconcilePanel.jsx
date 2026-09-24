"use client";

import { useEffect, useState } from "react";
import { FileCheck2, Upload } from "lucide-react";

import { bankAccounts as bankAccountsApi, sales } from "@/lib/api";
import { accountLabel } from "@/lib/bankChannels";
import { useI18n } from "../../app/providers/I18nProvider";
import { useToast } from "@/components/ui/Toast";
import { Badge, Button, Card, Field, Select } from "@/components/ui/kit";
import { errorText } from "@/lib/errors";

const money = (v) =>
  Number(v ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/**
 * Match a bank-app statement export (Bankak, Fawri, O-Cash…) against the
 * transfers recorded at the till. Preview shows what matched, what arrived
 * unrecorded, and what was recorded but never came; apply verifies the
 * matched ones — the statement is the second pair of eyes.
 */
export default function StatementReconcilePanel({ onApplied }) {
  const { t } = useI18n();
  const toast = useToast();
  const [accounts, setAccounts] = useState([]);
  const [account, setAccount] = useState("");
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    bankAccountsApi.list().then((r) => setAccounts(r.data.results ?? r.data)).catch(() => setAccounts([]));
  }, []);

  async function run(dryRun) {
    setError("");
    if (!account) return setError(t("finance.reconcileChooseAccount"));
    if (!file) return setError(t("finance.reconcileChooseFile"));
    setBusy(true);
    try {
      const form = new FormData();
      form.append("account", account);
      form.append("file", file);
      if (dryRun) form.append("dry_run", "1");
      const r = await sales.reconcilePayments(form);
      setResult(r.data);
      if (!dryRun) {
        toast.success(t("finance.reconcileApplied", { count: r.data.applied }));
        onApplied?.();
      }
    } catch (err) {
      setError(errorText(err, t, "finance.reconcileFailed"));
    } finally {
      setBusy(false);
    }
  }

  const outcomeTone = { verified: "ok", already_verified: "muted", self_recorded: "warn", amount_differs: "danger", needs_approver: "warn" };

  return (
    <Card className="mb-5 p-4 sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 font-display text-lg font-semibold">
          <FileCheck2 size={18} className="text-accent" />{t("finance.reconcileTitle")}
        </h2>
        <p className="text-xs text-muted">{t("finance.reconcileHint")}</p>
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        <Field label={t("sales.receivingAccount")}>
          <Select value={account} onChange={(e) => { setAccount(e.target.value); setResult(null); }}>
            <option value="">{t("common.select")}</option>
            {accounts.map((a) => <option key={a.id} value={a.id}>{accountLabel(t, a)}</option>)}
          </Select>
        </Field>
        <Field label={t("finance.reconcileFile")} hint={t("finance.reconcileFileHint")}>
          <input
            type="file" accept=".xlsx,.xlsm,.csv,.txt"
            className="block w-full text-sm text-muted file:me-3 file:rounded-control file:border file:border-line file:bg-surface file:px-3 file:py-1.5 file:text-sm file:text-ink"
            onChange={(e) => { setFile(e.target.files?.[0] || null); setResult(null); }}
          />
        </Field>
        <div className="flex items-end gap-2">
          <Button variant="outline" onClick={() => run(true)} disabled={busy}>
            <Upload size={15} /> {t("finance.reconcilePreview")}
          </Button>
          <Button onClick={() => run(false)} disabled={busy || !result || !result.matched?.length}>
            {t("finance.reconcileApply")}
          </Button>
        </div>
      </div>
      {error && <p className="mt-2 text-sm text-danger">{error}</p>}

      {result && (
        <div className="mt-4 space-y-4 text-sm">
          <div className="flex flex-wrap gap-2">
            <Badge tone="muted">{t("finance.reconcileRows", { count: result.rows })}</Badge>
            <Badge tone="ok">{t("finance.reconcileMatched", { count: result.matched.length })}</Badge>
            <Badge tone="warn">{t("finance.reconcileUnrecorded", { count: result.unmatched_rows.length })}</Badge>
            <Badge tone="danger">{t("finance.reconcileNotArrived", { count: result.unmatched_payments.length })}</Badge>
            {!result.dry_run && <Badge tone="accent">{t("finance.reconcileVerifiedCount", { count: result.applied })}</Badge>}
          </div>

          {result.matched.length > 0 && (
            <Section title={t("finance.reconcileMatchedTitle")}>
              {result.matched.map((m) => (
                <Row key={`m${m.row}`}>
                  <span dir="ltr" className="tabular text-muted">{m.reference}</span>
                  <span className="min-w-0 flex-1 truncate">
                    {m.payment.customer || t("sales.walkIn")} · <span dir="ltr">INV-{String(m.payment.invoice_number).padStart(6, "0")}</span>
                    {m.how === "last4_amount" && <span className="text-muted"> · {t("finance.reconcileByLast4")}</span>}
                    {m.payments?.length > 1 && <span className="text-muted"> · {t("finance.reconcileGroup", { count: m.payments.length })}</span>}
                  </span>
                  <span className="tabular font-semibold">{money(m.amount)}</span>
                  {m.amount_differs && <Badge tone="danger">{t("finance.reconcileRecorded", { amount: money(m.group_total ?? m.payment.amount) })}</Badge>}
                  {m.outcome && <Badge tone={outcomeTone[m.outcome] || "muted"}>{t(`finance.reconcileOutcome.${m.outcome}`)}</Badge>}
                </Row>
              ))}
            </Section>
          )}
          {result.unmatched_rows.length > 0 && (
            <Section title={t("finance.reconcileUnrecordedTitle")} hint={t("finance.reconcileUnrecordedHint")}>
              {result.unmatched_rows.map((u) => (
                <Row key={`u${u.row}`}>
                  <span dir="ltr" className="tabular text-muted">{u.reference || "—"}</span>
                  <span className="min-w-0 flex-1 truncate text-muted">{u.sender || ""} {u.date ? `· ${u.date}` : ""}</span>
                  <span className="tabular font-semibold">{u.amount != null ? money(u.amount) : "—"}</span>
                  <Badge tone="muted">{t(`finance.reconcileReason.${u.reason}`)}</Badge>
                </Row>
              ))}
            </Section>
          )}
          {result.unmatched_payments.length > 0 && (
            <Section title={t("finance.reconcileNotArrivedTitle")} hint={t("finance.reconcileNotArrivedHint")}>
              {result.unmatched_payments.map((p) => (
                <Row key={`p${p.id}`}>
                  <span dir="ltr" className="tabular text-muted">{p.transfer_reference || `#${p.reference_last4}`}</span>
                  <span className="min-w-0 flex-1 truncate">
                    {p.customer || t("sales.walkIn")} · <span dir="ltr">INV-{String(p.invoice_number).padStart(6, "0")}</span>
                    <span className="text-muted"> · {p.sender_bank_name}</span>
                  </span>
                  <span className="tabular font-semibold">{money(p.amount)}</span>
                </Row>
              ))}
            </Section>
          )}
        </div>
      )}
    </Card>
  );
}

function Section({ title, hint, children }) {
  return (
    <div>
      <div className="mb-1 flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-semibold">{title}</h3>
        {hint && <span className="text-xs text-muted">{hint}</span>}
      </div>
      <div className="divide-y divide-line rounded-card border border-line">{children}</div>
    </div>
  );
}

function Row({ children }) {
  return <div className="flex flex-wrap items-center gap-3 px-3 py-2">{children}</div>;
}
