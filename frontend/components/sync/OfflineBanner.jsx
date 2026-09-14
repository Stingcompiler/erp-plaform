"use client";

import { CloudOff, RefreshCw } from "lucide-react";

import { useSync } from "@/components/sync/SyncProvider";
import { useAuth } from "../../app/providers/AuthProvider";
import { useI18n } from "../../app/providers/I18nProvider";

// Full-width, unmissable state for a market where the connection drops
// daily: the cashier must know they are working locally, how much is
// waiting to upload, and how fresh the local catalogue is. The small cloud
// icon in the topbar stays for the normal case; this only appears when it
// matters.
export default function OfflineBanner() {
  const { online, pending, flushing, flush, lastPulledAt, lastSyncedAt } = useSync();
  const { offlineSession } = useAuth();
  const { t, language } = useI18n();
  if (online && !offlineSession && !pending) return null;
  const when = (value) =>
    value ? new Date(value).toLocaleString(language === "ar" ? "ar" : "en", { dateStyle: "short", timeStyle: "short" }) : "—";
  const offline = !online || offlineSession;
  return (
    <div
      role="status"
      aria-live="polite"
      className={`flex flex-wrap items-center justify-between gap-2 border-b px-4 py-2 text-sm ${
        offline ? "border-warn/40 bg-warn/10 text-ink" : "border-accent/30 bg-accent/5 text-ink"
      }`}
    >
      <div className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-1">
        <span className="inline-flex items-center gap-2 font-medium">
          {offline ? <CloudOff size={16} className="text-warn" /> : <RefreshCw size={16} className={flushing ? "animate-spin" : ""} />}
          {offline ? t("sync.bannerOffline") : t("sync.bannerPending", { count: pending })}
        </span>
        {offline && pending > 0 && <span className="text-muted">{t("sync.bannerQueued", { count: pending })}</span>}
        <span className="text-muted">{t("sync.bannerCatalogue", { time: when(lastPulledAt) })}</span>
        {lastSyncedAt && <span className="text-muted">{t("sync.bannerLastSync", { time: when(lastSyncedAt) })}</span>}
      </div>
      {online && pending > 0 && (
        <button
          type="button"
          onClick={() => flush(true)}
          disabled={flushing}
          className="rounded-control border border-line bg-surface px-3 py-1 text-sm font-medium hover:border-accent disabled:opacity-60"
        >
          {t("sync.syncNow")}
        </button>
      )}
    </div>
  );
}
