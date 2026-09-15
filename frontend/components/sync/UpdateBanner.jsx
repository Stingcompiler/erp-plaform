"use client";

import { ArrowDownToLine } from "lucide-react";

import { useServiceWorkerUpdate } from "@/lib/registerServiceWorker";
import { useSync } from "@/components/sync/SyncProvider";
import { useI18n } from "../../app/providers/I18nProvider";

// A new build is installed and waiting. Applying it reloads the page, so
// the button is only live when nothing would be lost: no queued sales and
// a reachable server. It never applies itself while someone is signed in —
// a cart on screen is not persisted.
export default function UpdateBanner() {
  const { updateReady, applyUpdate } = useServiceWorkerUpdate();
  const { online, pending } = useSync();
  const { t } = useI18n();
  if (!updateReady) return null;
  const blocked = !online || pending > 0;
  return (
    <div role="status" className="flex flex-wrap items-center justify-between gap-2 border-b border-accent/30 bg-accent/5 px-4 py-2 text-sm text-ink">
      <span className="inline-flex items-center gap-2 font-medium">
        <ArrowDownToLine size={16} />
        {t("update.ready")}
        {blocked && <span className="font-normal text-muted">{t(pending > 0 ? "update.waitQueue" : "update.waitOnline")}</span>}
      </span>
      <button
        type="button"
        onClick={() => applyUpdate()}
        disabled={blocked}
        className="rounded-control border border-line bg-surface px-3 py-1 text-sm font-medium hover:border-accent disabled:opacity-60"
      >
        {t("update.apply")}
      </button>
    </div>
  );
}
