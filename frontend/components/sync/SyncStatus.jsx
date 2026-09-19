"use client";
import { useState } from "react";
import { Cloud, CloudOff, RefreshCw, AlertTriangle, Download, ShieldCheck, ShieldAlert } from "lucide-react";
import { installRoute, useInstallPrompt } from "@/lib/installPrompt";
import { useSync } from "@/components/sync/SyncProvider";
import { useI18n } from "../../app/providers/I18nProvider";
import Drawer from "@/components/ui/Drawer";
import { Button } from "@/components/ui/kit";
import AttentionBadge from "@/components/attention/AttentionBadge";

const money = (v) => Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

// One line a person recognises the operation by: how much, how many items,
// which day — never ids.
function summarise(op, t, language) {
  const p = op.payload || {};
  const parts = [];
  const amount = p.amount ?? p.payment?.amount;
  if (amount !== undefined && amount !== null && amount !== "") parts.push(money(amount));
  if (Array.isArray(p.lines) && p.lines.length) parts.push(t("improvements.syncItems", { count: p.lines.length }));
  const day = p.date || p.occurred_at || p.recorded_at;
  if (day) {
    const d = new Date(day);
    if (!Number.isNaN(d.getTime())) parts.push(d.toLocaleDateString(language === "ar" ? "ar" : "en", { dateStyle: "medium" }));
  }
  if (p.status && op.op_type === "attendance") parts.push(t(`hr.attendance.status.${p.status}`));
  return parts.join(" · ");
}

export default function SyncStatus() {
  const { online, pending, flushing, flush, discard, operations, error, legacy, persisted, storageLow } = useSync();
  const [discarding, setDiscarding] = useState(null);
  const [reason, setReason] = useState("");
  const { installed, canPrompt, prompt } = useInstallPrompt();
  const { t, language } = useI18n();
  const [open, setOpen] = useState(false);
  const failedCount = operations.filter((op) => op.error).length;
  const failed = failedCount > 0;
  const Icon = error || failed || legacy ? AlertTriangle : online ? Cloud : CloudOff;
  const errorKey = { storage: "syncStorage", network: "syncNetwork", identity: "syncIdentity", auth: "syncAuth" }[error];
  return <>
    <button onClick={() => setOpen(true)} title={t("improvements.syncReview")}
      className={`flex items-center gap-1.5 rounded-control px-2 py-1.5 text-sm ${error || failed ? "text-danger" : "text-muted"}`}>
      <Icon size={16} /><span>{online ? t("sync.sync") : t("sync.offline")} {pending || ""}</span>
      {/* Operations that failed to sync are this device's own attention
          item: nothing on the server knows about them yet. */}
      <AttentionBadge count={failedCount} tone="danger" />
    </button>
    <Drawer open={open} onClose={() => setOpen(false)} title={t("improvements.syncTitle")}
      footer={<Button onClick={() => flush(true)} disabled={!online || flushing || !pending}>
        <RefreshCw size={16} className={flushing ? "animate-spin" : ""} />{t("improvements.retry")}
      </Button>}>
      <p className="mb-4 text-sm text-muted">{t("improvements.syncNote")}</p>
      {/* Whether queued sales are actually safe on this device. Durable
          storage is what the browser grants an installed app; a plain tab's
          data can be evicted, so the two rows are shown together. */}
      <div className="mb-4 space-y-2 rounded-card border border-line p-3 text-sm" data-testid="device-storage">
        <div className="flex items-center gap-2">
          {persisted ? <ShieldCheck size={16} className="text-ok" /> : <ShieldAlert size={16} className="text-warn" />}
          <span>{persisted ? t("install.storageDurable") : persisted === null ? t("install.storageUnknown") : t("install.storageBestEffort")}</span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Download size={16} className="text-muted" />
          <span className="flex-1">{installed ? t("install.installed") : t("install.notInstalled")}</span>
          {canPrompt && (
            <button type="button" onClick={() => prompt()}
              className="rounded-control border border-line bg-surface px-3 py-1 text-sm font-medium hover:border-accent">
              {t("install.button")}
            </button>
          )}
        </div>
        {!installed && !canPrompt && (
          <p className="text-xs text-muted">{t(`install.route.${installRoute()}`)}</p>
        )}
        {storageLow && <p role="alert" className="text-xs text-danger">{t("install.storageLow")}</p>}
      </div>
      {errorKey && <p role="alert" className="mb-3 text-sm text-danger">{t(`improvements.${errorKey}`)}</p>}
      {error === "auth" && (
        <a href="/login/" className="mb-3 inline-block rounded-control border border-line px-3 py-1 text-sm font-medium hover:border-accent">
          {t("improvements.signInAgain")}
        </a>
      )}
      {legacy && <p role="alert" className="mb-3 rounded-control bg-warn/10 p-3 text-sm text-warn">{t("improvements.syncLegacy")}</p>}
      {!pending && !error && <p>{t("improvements.syncEmpty")}</p>}
      <ul className="space-y-3">{operations.map((op) => <li key={op.client_uuid} className={`rounded-card border p-3 text-sm ${op.error ? "border-danger/40 bg-danger/5" : "border-line"}`}>
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="font-medium">{t(`sync.ops.${op.op_type}`).startsWith("sync.ops.") ? op.op_type : t(`sync.ops.${op.op_type}`)}</div>
            <div className="mt-0.5 text-xs text-muted">{summarise(op, t, language)}</div>
          </div>
          <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${op.error ? "bg-danger/10 text-danger" : "bg-paper text-muted"}`}>
            {t(op.error ? "improvements.syncFailed" : "improvements.syncPending")}
          </span>
        </div>
        {op.error ? (
          <div className="mt-2 rounded-control bg-surface p-2">
            <p className="break-words text-ink">{op.error}</p>
            <p className="mt-1 text-xs text-muted">{t("improvements.syncFailedHint")}</p>
          </div>
        ) : (
          <p className="mt-2 text-xs text-muted">{t(online ? "improvements.syncPendingHint" : "improvements.syncOfflineHint")}</p>
        )}
        <details className="mt-2 text-xs text-muted">
          <summary className="cursor-pointer select-none">{t("improvements.technicalDetails")}</summary>
          <div className="mt-1 break-all font-mono">{op.client_uuid}</div>
          {op.queued_at && <div className="mt-0.5">{new Date(op.queued_at).toLocaleString(language === "ar" ? "ar" : "en")}</div>}
        </details>
        {op.error && online && (
          discarding === op.client_uuid ? (
            <div className="mt-2 space-y-2">
              <input className="w-full rounded-control border border-line bg-surface px-2 py-1 text-sm"
                placeholder={t("improvements.discardReason")} value={reason}
                onChange={(e) => setReason(e.target.value)} />
              <div className="flex gap-2">
                <Button variant="danger" disabled={!reason.trim()}
                  onClick={async () => { await discard(op.client_uuid, reason.trim()); setDiscarding(null); setReason(""); }}>
                  {t("improvements.discardConfirm")}
                </Button>
                <Button variant="ghost" onClick={() => setDiscarding(null)}>{t("common.cancel")}</Button>
              </div>
            </div>
          ) : (
            <button type="button" onClick={() => setDiscarding(op.client_uuid)}
              className="mt-2 text-sm text-danger hover:underline">{t("improvements.syncDiscard")}</button>
          )
        )}
      </li>)}</ul>
    </Drawer>
  </>;
}
