"use client";
import { useEffect, useId, useRef, useState } from "react";
import { X } from "lucide-react";
import { useI18n } from "../../app/providers/I18nProvider";
import { Button } from "./kit";

export default function Drawer({ open, onClose, title, children, footer, wide, protectChanges = true }) {
  const { t } = useI18n();
  const ref = useRef(null);
  const titleId = useId();
  const dirty = useRef(false);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  const [confirm, setConfirm] = useState(false);
  const requestClose = () => {
    if (protectChanges && dirty.current) setConfirm(true);
    else closeRef.current();
  };
  const requestCloseRef = useRef(requestClose);
  requestCloseRef.current = requestClose;
  useEffect(() => {
    if (!open) return;
    dirty.current = false; setConfirm(false);
    const previous = document.activeElement;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const panel = ref.current;
    panel?.focus();
    const keydown = (e) => {
      const dialogs = document.querySelectorAll("[data-erp-dialog]");
      if (dialogs[dialogs.length-1] !== panel) return;
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); requestCloseRef.current(); }
      if (e.key === "Tab") {
        const items = [...panel.querySelectorAll('button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex="0"]')]
          .filter((el) => el.getClientRects().length > 0);
        const first = items[0], last = items[items.length-1];
        if (!first) { e.preventDefault(); panel.focus(); }
        else if (e.shiftKey && (document.activeElement === first || !panel.contains(document.activeElement) || document.activeElement === panel)) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && (document.activeElement === last || !panel.contains(document.activeElement))) { e.preventDefault(); first.focus(); }
      }
    };
    const unload = (e) => { if (protectChanges && dirty.current) { e.preventDefault(); e.returnValue = ""; } };
    document.addEventListener("keydown", keydown);
    window.addEventListener("beforeunload", unload);
    return () => {
      document.removeEventListener("keydown", keydown);
      window.removeEventListener("beforeunload", unload);
      document.body.style.overflow = overflow;
      if (previous?.isConnected) previous.focus();
    };
  }, [open, protectChanges]);
  useEffect(() => {
    if (confirm) ref.current?.querySelector('[data-keep-editing]')?.focus();
    else if (open) ref.current?.focus();
  }, [confirm, open]);
  if (!open) return null;
  return <div className="fixed inset-0 z-40">
    <div className="absolute inset-0 bg-black/45" onClick={requestClose} aria-hidden="true" />
    <div ref={ref} tabIndex={-1} data-erp-dialog role="dialog" aria-modal="true" aria-labelledby={titleId}
      className={`absolute inset-y-0 end-0 flex w-full flex-col bg-surface shadow-xl ${wide ? "max-w-3xl" : "max-w-md"}`}
      onChangeCapture={() => { dirty.current = true; }}>
      <div className="flex items-center justify-between border-b border-line px-5 py-4">
        <h2 id={titleId} className="font-display text-lg font-semibold">{confirm ? t("improvements.discardTitle") : title}</h2>
        <button onClick={requestClose} aria-label={t("common.close")} className="rounded-control p-2 text-muted"><X size={18} /></button>
      </div>
      {confirm && <div className="space-y-4 p-5">
        <p>{t("improvements.discardBody")}</p>
        <div className="flex flex-wrap gap-2">
          <Button data-keep-editing onClick={() => setConfirm(false)}>{t("improvements.keepEditing")}</Button>
          <Button variant="danger" onClick={() => { dirty.current=false; closeRef.current(); }}>{t("improvements.discard")}</Button>
        </div>
      </div>}
      <div className={confirm ? "hidden" : "flex-1 overflow-y-auto px-5 py-4"}>{children}</div>
      {footer && <div className={confirm ? "hidden" : "border-t border-line px-5 py-4"}
        onClickCapture={(e) => {
          // Existing consumers own save callbacks. Guard their explicit Cancel
          // buttons without intercepting successful save -> close callbacks.
          const button = e.target.closest("button");
          if (button?.textContent.trim() === t("common.cancel") && protectChanges && dirty.current) {
            e.preventDefault(); e.stopPropagation(); setConfirm(true);
          }
        }}>{footer}</div>}
    </div>
  </div>;
}
