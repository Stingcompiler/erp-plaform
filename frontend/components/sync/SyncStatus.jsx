"use client";

import { Cloud, CloudOff, RefreshCw } from "lucide-react";

import { useSync } from "@/components/sync/SyncProvider";
import { useI18n } from "../../app/providers/I18nProvider";

export default function SyncStatus() {
  const { online, pending, flushing, flush } = useSync();
  const { t } = useI18n();

  if (online && pending === 0) {
    return (
      <span
        className="flex items-center gap-1.5 rounded-control px-2.5 py-1.5 text-sm text-muted"
        title={t("sync.allSynced")}
      >
        <Cloud size={16} />
        {t("sync.synced")}
      </span>
    );
  }

  return (
    <button
      onClick={flush}
      disabled={!online || flushing}
      title={online ? t("sync.syncNow") : t("sync.offlineQueued")}
      className={`flex items-center gap-1.5 rounded-control px-2.5 py-1.5 text-sm ${
        online ? "text-accent hover:bg-paper" : "text-danger"
      }`}
    >
      {online ? (
        <RefreshCw size={16} className={flushing ? "animate-spin" : ""} />
      ) : (
        <CloudOff size={16} />
      )}
      {online ? (pending > 0 ? `${t("sync.sync")} ${pending}` : t("sync.sync")) : `${t("sync.offline")} · ${pending}`}
    </button>
  );
}
