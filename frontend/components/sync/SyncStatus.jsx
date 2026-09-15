"use client";
import { useState } from "react";
import { Cloud, CloudOff, RefreshCw, AlertTriangle, Download, ShieldCheck, ShieldAlert } from "lucide-react";
import { useInstallPrompt } from "@/lib/installPrompt";
import { useSync } from "@/components/sync/SyncProvider";
import { useI18n } from "../../app/providers/I18nProvider";
import Drawer from "@/components/ui/Drawer";
import { Button } from "@/components/ui/kit";
import AttentionBadge from "@/components/attention/AttentionBadge";

export default function SyncStatus() {
  const { online, pending, flushing, flush, operations, error, legacy, persisted, storageLow } = useSync();
  const { installed, canPrompt, prompt } = useInstallPrompt();
  const { t } = useI18n();
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
        {!installed && !canPrompt && <p className="text-xs text-muted">{t("install.manualHint")}</p>}
        {storageLow && <p role="alert" className="text-xs text-danger">{t("install.storageLow")}</p>}
      </div>
      {errorKey && <p role="alert" className="mb-3 text-sm text-danger">{t(`improvements.${errorKey}`)}</p>}
      {legacy && <p role="alert" className="mb-3 rounded-control bg-warn/10 p-3 text-sm text-warn">{t("improvements.syncLegacy")}</p>}
      {!pending && !error && <p>{t("improvements.syncEmpty")}</p>}
      <ul className="space-y-3">{operations.map((op) => <li key={op.client_uuid} className="rounded-card border border-line p-3 text-sm">
        <div className="font-medium">{t(`sync.ops.${op.op_type}`).startsWith("sync.ops.") ? op.op_type : t(`sync.ops.${op.op_type}`)}</div>
        <div className="mt-1 break-all font-mono text-xs text-muted">{op.client_uuid}</div>
        <div className={op.error ? "mt-2 text-danger" : "mt-2 text-muted"}>{t(op.error ? "improvements.syncFailed" : "improvements.syncPending")}</div>
        {op.error && <p className="mt-1 break-words text-danger">{op.error}</p>}
      </li>)}</ul>
    </Drawer>
  </>;
}
