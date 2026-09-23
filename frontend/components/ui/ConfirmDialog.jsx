"use client";

// The product's own confirmation dialog, in place of window.confirm.
//
// The browser's box ignores the page direction and theme, cannot say which
// button is the dangerous one, and looks like a warning from the browser
// rather than from the shop's own system — people click through it. This
// one reads right-to-left, uses the danger colour for irreversible actions,
// puts the focus on "cancel" so Enter never destroys anything by accident,
// and closes on Escape or a click outside.
//
//   const confirm = useConfirm();
//   if (!(await confirm(t("users.removeConfirm", { email }), { tone: "danger" }))) return;
//
// With `input` it also asks for a line of text (a reason, a note) and
// resolves to that text, or to false when cancelled — replacing
// window.prompt the same way:
//
//   const reason = await confirm(t("…"), { input: { label: t("…"), required: true } });
//   if (reason === false) return;

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { AlertTriangle, HelpCircle } from "lucide-react";

import { useI18n } from "../../app/providers/I18nProvider";

const ConfirmContext = createContext(null);

export function useConfirm() {
  const confirm = useContext(ConfirmContext);
  // Outside the provider (a page rendered on its own) the browser box still
  // works, so nothing ever proceeds without asking.
  return confirm || ((message, options = {}) => Promise.resolve(
    options.input ? (window.prompt(message) ?? false) : window.confirm(message)
  ));
}

export function ConfirmProvider({ children }) {
  const { t } = useI18n();
  const [request, setRequest] = useState(null);
  const [text, setText] = useState("");
  const cancelRef = useRef(null);
  const resolverRef = useRef(null);

  const confirm = useCallback((message, options = {}) => new Promise((resolve) => {
    resolverRef.current = resolve;
    setText(options.input?.initial || "");
    setRequest({ message, ...options });
  }), []);

  const close = useCallback((answer) => {
    resolverRef.current?.(answer);
    resolverRef.current = null;
    setRequest(null);
  }, []);

  const inputRef = useRef(null);
  useEffect(() => {
    if (!request) return undefined;
    (request.input ? inputRef.current : cancelRef.current)?.focus();
    const onKey = (event) => { if (event.key === "Escape") close(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [request, close]);

  const danger = request?.tone === "danger";
  const missing = Boolean(request?.input?.required && !text.trim());
  const accept = () => {
    if (missing) return;
    close(request.input ? text.trim() : true);
  };
  const Icon = danger ? AlertTriangle : HelpCircle;

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {request && (
        <div className="fixed inset-0 z-50 flex items-end justify-center p-0 sm:items-center sm:p-4">
          <div className="absolute inset-0 bg-black/50" onClick={() => close(false)} aria-hidden="true" />
          <div
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="confirm-title"
            aria-describedby="confirm-message"
            className="relative w-full max-w-md rounded-t-card border border-line bg-surface p-5 shadow-card sm:rounded-card"
          >
            <div className="flex items-start gap-3">
              <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-full ${danger ? "bg-danger/10 text-danger" : "bg-accent/10 text-accent"}`}>
                <Icon size={20} />
              </span>
              <div className="min-w-0">
                <h2 id="confirm-title" className="font-display text-base font-semibold text-ink">
                  {request.title || t(danger ? "confirm.titleDanger" : "confirm.title")}
                </h2>
                <p id="confirm-message" className="mt-1 whitespace-pre-line text-sm text-muted">{request.message}</p>
              </div>
            </div>
            {request.input && (
              <label className="mt-4 block text-sm">
                <span className="mb-1 block font-medium text-ink">{request.input.label}</span>
                <textarea
                  ref={inputRef}
                  rows={3}
                  value={text}
                  onChange={(event) => setText(event.target.value)}
                  onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); accept(); } }}
                  className="w-full rounded-control border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-accent"
                />
              </label>
            )}
            <div className="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              <button
                ref={cancelRef}
                type="button"
                onClick={() => close(false)}
                className="min-h-11 rounded-control border border-line bg-surface px-4 text-sm font-medium text-ink hover:bg-paper"
              >
                {request.cancelLabel || t("common.cancel")}
              </button>
              <button
                type="button"
                onClick={accept}
                disabled={missing}
                className={`min-h-11 rounded-control px-4 text-sm font-semibold text-white disabled:opacity-50 ${danger ? "bg-danger hover:opacity-90" : "bg-accent hover:bg-accent-strong"}`}
              >
                {request.confirmLabel || t(danger ? "confirm.proceedDanger" : "confirm.proceed")}
              </button>
            </div>
          </div>
        </div>
      )}
    </ConfirmContext.Provider>
  );
}
