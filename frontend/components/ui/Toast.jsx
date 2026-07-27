"use client";

import { createContext, useCallback, useContext, useState } from "react";
import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";

const ToastContext = createContext(null);

const NOOP = { push: () => {}, success: () => {}, error: () => {}, info: () => {} };

export function useToast() {
  return useContext(ToastContext) || NOOP;
}

const TONE = {
  success: { icon: CheckCircle2, cls: "border-ok/30 text-ok" },
  error: { icon: AlertCircle, cls: "border-danger/30 text-danger" },
  info: { icon: Info, cls: "border-line text-ink" },
};

function ToastItem({ toast, onClose }) {
  const { icon: Icon, cls } = TONE[toast.tone] || TONE.info;
  return (
    <div
      role="status"
      className={`pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-card border bg-surface px-4 py-3 shadow-card ${cls}`}
    >
      <Icon size={18} className="mt-0.5 shrink-0" />
      <p className="flex-1 text-sm text-ink">{toast.message}</p>
      <button
        onClick={onClose}
        className="shrink-0 text-muted hover:text-ink"
        aria-label="Dismiss"
      >
        <X size={15} />
      </button>
    </div>
  );
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const remove = useCallback((id) => {
    setToasts((list) => list.filter((t) => t.id !== id));
  }, []);

  const push = useCallback(
    (message, opts = {}) => {
      const id = Math.random().toString(36).slice(2);
      const duration = opts.duration ?? 4000;
      setToasts((list) => [...list, { id, message, tone: opts.tone || "info" }]);
      if (duration > 0) setTimeout(() => remove(id), duration);
      return id;
    },
    [remove]
  );

  const api = {
    push,
    success: (m, o) => push(m, { ...o, tone: "success" }),
    error: (m, o) => push(m, { ...o, tone: "error" }),
    info: (m, o) => push(m, { ...o, tone: "info" }),
  };

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 bottom-4 z-50 flex flex-col items-center gap-2 px-4">
        {toasts.map((t) => (
          <ToastItem key={t.id} toast={t} onClose={() => remove(t.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}
