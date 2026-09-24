"use client";

import { ArrowDownToLine } from "lucide-react";

import { useServiceWorkerUpdate } from "@/lib/registerServiceWorker";
import { useSync } from "@/components/sync/SyncProvider";
import { waitingToSend } from "@/lib/syncRetry";
import { useI18n } from "../../app/providers/I18nProvider";

// A new build is installed and waiting. Applying it reloads the page, so
// the button is only live when nothing would be lost: no sales still being
// sent and a reachable server. It never applies itself while someone is signed in —
// a cart on screen is not persisted.
export default function UpdateBanner() {
  const { updateReady, applyUpdate } = useServiceWorkerUpdate();
  const { online, operations } = useSync();
  const { t } = useI18n();
  if (!updateReady) return null;
  // Only items still on their way hold the update back. A refused item is
  // not going anywhere on its own (it waits for a repair or a discard) and is
  // kept on the device across the reload; blocking on it kept the old build
  // — and its bugs — running for as long as the item sat there.
  const pending = waitingToSend(operations);
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
        className="tap rounded-control border border-line bg-surface px-3 py-1 text-sm font-medium hover:border-accent disabled:opacity-60"
      >
        {t("update.apply")}
      </button>
    </div>
  );
}
