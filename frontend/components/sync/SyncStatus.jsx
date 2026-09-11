"use client";
import { useState } from "react";
import { Cloud, CloudOff, RefreshCw, AlertTriangle } from "lucide-react";
import { useSync } from "@/components/sync/SyncProvider";
import { useI18n } from "../../app/providers/I18nProvider";
import Drawer from "@/components/ui/Drawer";
import { Button } from "@/components/ui/kit";

export default function SyncStatus() {
  const { online, pending, flushing, flush, operations, error, legacy } = useSync();
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const failed = operations.some((op) => op.error);
  const Icon = error || failed || legacy ? AlertTriangle : online ? Cloud : CloudOff;
  const errorKey = { storage: "syncStorage", network: "syncNetwork", identity: "syncIdentity" }[error];
  return <>
    <button onClick={() => setOpen(true)} title={t("improvements.syncReview")}
      className={`flex items-center gap-1.5 rounded-control px-2 py-1.5 text-sm ${error || failed ? "text-danger" : "text-muted"}`}>
      <Icon size={16} /><span>{online ? t("sync.sync") : t("sync.offline")} {pending || ""}</span>
    </button>
    <Drawer open={open} onClose={() => setOpen(false)} title={t("improvements.syncTitle")}
      footer={<Button onClick={() => flush(true)} disabled={!online || flushing || !pending}>
        <RefreshCw size={16} className={flushing ? "animate-spin" : ""} />{t("improvements.retry")}
      </Button>}>
      <p className="mb-4 text-sm text-muted">{t("improvements.syncNote")}</p>
      {errorKey && <p role="alert" className="mb-3 text-sm text-danger">{t(`improvements.${errorKey}`)}</p>}
      {legacy && <p role="alert" className="mb-3 rounded-control bg-warn/10 p-3 text-sm text-warn">{t("improvements.syncLegacy")}</p>}
      {!pending && !error && <p>{t("improvements.syncEmpty")}</p>}
      <ul className="space-y-3">{operations.map((op) => <li key={op.client_uuid} className="rounded-card border border-line p-3 text-sm">
        <div className="font-medium">{op.op_type === "pos_checkout" ? t("sales.pos") : op.op_type}</div>
        <div className="mt-1 break-all font-mono text-xs text-muted">{op.client_uuid}</div>
        <div className={op.error ? "mt-2 text-danger" : "mt-2 text-muted"}>{t(op.error ? "improvements.syncFailed" : "improvements.syncPending")}</div>
        {op.error && <p className="mt-1 break-words text-danger">{op.error}</p>}
      </li>)}</ul>
    </Drawer>
  </>;
}
