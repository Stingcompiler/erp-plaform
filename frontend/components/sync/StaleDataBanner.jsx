"use client";

import { useEffect, useState } from "react";
import { History } from "lucide-react";
import { usePathname } from "next/navigation";

import { useI18n } from "../../app/providers/I18nProvider";
import { clearStale, getStale, subscribeStale } from "@/lib/staleData";

/**
 * Shown when the screen is populated from remembered responses because the
 * server could not be reached. The figures are real — they are just from
 * the time shown — and a person about to collect a debt or read a report
 * needs to know that before acting on them.
 */
export default function StaleDataBanner() {
  const { t, language } = useI18n();
  const pathname = usePathname();
  const [staleAt, setStaleAt] = useState(getStale());

  useEffect(() => subscribeStale(setStaleAt), []);
  // A new page starts clean; whatever it loads decides again.
  useEffect(() => { clearStale(); }, [pathname]);

  if (!staleAt) return null;
  const when = new Date(staleAt).toLocaleString(language === "ar" ? "ar" : "en", { dateStyle: "short", timeStyle: "short" });
  return (
    <div role="status" aria-live="polite" className="flex flex-wrap items-center gap-2 border-b border-warn/40 bg-warn/10 px-4 py-2 text-sm text-ink">
      <History size={16} className="text-warn" />
      <span className="font-medium">{t("sync.staleTitle")}</span>
      <span className="text-muted">{t("sync.staleBody", { time: when })}</span>
    </div>
  );
}
