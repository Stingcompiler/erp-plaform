"use client";

// The body of one report card in whatever state its request is in — see
// lib/reportSlots.js. Loading shows the card's shape, a failure says so with
// a retry for this card alone, an empty answer says "no data for this
// period", and only a real answer renders the figures.

import { RotateCw } from "lucide-react";

import { useI18n } from "../../app/providers/I18nProvider";
import { Button } from "@/components/ui/kit";
import { SkeletonLines } from "@/components/ui/Skeleton";
import { isEmptyReport } from "@/lib/reportSlots";

export function ReportFailed({ status, onRetry, compact = false }) {
  const { t } = useI18n();
  if (status === "forbidden" || status === "locked") {
    return (
      <p className="py-2 text-sm text-muted">
        {t(status === "locked" ? "states.reportNotInPlan" : "states.reportForbidden")}
      </p>
    );
  }
  return (
    <div role="alert" className={`flex flex-wrap items-center gap-2 text-sm ${compact ? "" : "py-4"}`}>
      <span className="text-danger">{t("states.reportFailed")}</span>
      {onRetry && (
        <Button variant="outline" onClick={onRetry} className="px-2.5 text-xs">
          <RotateCw size={13} /> {t("improvements.retry")}
        </Button>
      )}
    </div>
  );
}

export default function ReportState({ slot, onRetry, isEmpty = isEmptyReport, emptyText, lines = 3, children }) {
  const { t } = useI18n();
  const status = slot?.status || "loading";
  if (status === "loading") return <SkeletonLines lines={lines} />;
  if (status !== "ok") return <ReportFailed status={status} onRetry={onRetry} />;
  if (isEmpty(slot.data)) {
    return <p className="py-6 text-center text-sm text-muted">{emptyText || t("reports.noData")}</p>;
  }
  return children(slot.data);
}
