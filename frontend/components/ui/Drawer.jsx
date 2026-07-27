"use client";

import { useEffect } from "react";
import { X } from "lucide-react";

import { useI18n } from "../../app/providers/I18nProvider";

// `wide` is for document previews — an invoice's line table is unreadable in
// the default form-width panel.
export default function Drawer({ open, onClose, title, children, footer, wide }) {
  const { t } = useI18n();
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-40" role="dialog" aria-modal="true">
      <div
        className="absolute inset-0 bg-ink/40"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        className={`absolute inset-y-0 end-0 flex w-full flex-col bg-surface shadow-xl ${
          wide ? "max-w-3xl" : "max-w-md"
        }`}
      >
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <h2 className="font-display text-lg font-semibold text-ink">{title}</h2>
          <button
            onClick={onClose}
            aria-label={t("common.close")}
            className="rounded-control p-1.5 text-muted hover:bg-paper hover:text-ink"
          >
            <X size={18} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {footer && (
          <div className="border-t border-line px-5 py-4">{footer}</div>
        )}
      </div>
    </div>
  );
}
