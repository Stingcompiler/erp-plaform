"use client";

import { cloneElement, forwardRef, isValidElement, useId } from "react";

export function Button({ variant = "primary", className = "", ...props }) {
  const base =
    "tap inline-flex items-center justify-center gap-2 min-h-10 rounded-control px-4 py-2 text-sm font-semibold transition-colors disabled:opacity-50 disabled:pointer-events-none";
  const variants = {
    primary: "bg-accent text-white shadow-sm hover:bg-accent-strong",
    ghost: "text-muted hover:bg-paper hover:text-ink",
    outline: "border border-line bg-surface text-ink shadow-sm hover:border-accent/40 hover:bg-paper",
    danger: "bg-danger text-white hover:opacity-90",
  };
  return <button className={`${base} ${variants[variant]} ${className}`} {...props} />;
}

// A labelled control with its hint and error wired for assistive tech: the
// control gets a stable id, `aria-describedby` points at the hint/error text,
// and `aria-invalid` follows `error`. Callers keep passing a bare <Input>;
// nothing changes visually unless `error` is set.
export function Field({ label, hint, error, children }) {
  const generated = useId();
  const control = isValidElement(children) ? children : null;
  const id = control?.props?.id || generated;
  const hintId = hint ? `${id}-hint` : null;
  const errorId = error ? `${id}-error` : null;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;
  const child = control
    ? cloneElement(control, {
        id,
        "aria-describedby": describedBy,
        "aria-invalid": error ? true : undefined,
      })
    : children;
  return (
    <div className="block">
      <label htmlFor={id} className="mb-1 block text-sm font-medium text-ink">{label}</label>
      {child}
      {hint && <span id={hintId} className="mt-1 block text-xs text-muted">{hint}</span>}
      {error && <span id={errorId} role="alert" className="mt-1 block text-xs text-danger">{error}</span>}
    </div>
  );
}

export const controlClass =
  "tap w-full rounded-control border border-line bg-surface min-h-10 px-3 py-2 text-sm text-ink shadow-sm outline-none transition-colors hover:border-muted/40 focus:border-accent focus:ring-2 focus:ring-accent/15";

// forwardRef so callers can focus the field programmatically — the barcode
// scanner relies on refocusing after every scan.
// A caller passing its own width (`w-20`, `w-28`) means it; controlClass's
// `w-full` must yield to it instead of racing it in the stylesheet order.
function sized(className) {
  return /\bw-\S+/.test(className) ? controlClass.replace("w-full ", "") : controlClass;
}

// A date or time control lays its fields out in the page direction: on an
// Arabic (RTL) page "10/05/2026, 01:40" came out reordered as
// "10 / 05 / 2026 , 40 : 1". Its fields are Latin-ordered, so it is LTR
// unless a caller says otherwise.
const LTR_TYPES = new Set(["date", "datetime-local", "time", "month", "week"]);

export const Input = forwardRef(function Input({ className = "", ...props }, ref) {
  const dir = props.dir ?? (LTR_TYPES.has(props.type) ? "ltr" : undefined);
  return <input ref={ref} className={`${sized(className)} ${className}`} {...props} dir={dir} />;
});

export function Select({ className = "", children, ...props }) {
  return (
    <select className={`${sized(className)} ${className}`} {...props}>
      {children}
    </select>
  );
}

export function Badge({ tone = "muted", children }) {
  const tones = {
    muted: "bg-paper text-muted",
    ok: "bg-ok/10 text-ok",
    warn: "bg-warn/10 text-warn",
    danger: "bg-danger/10 text-danger",
    accent: "bg-accent/10 text-accent",
  };
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

export function Card({ className = "", children }) {
  return (
    <div className={`workspace-card rounded-card border border-line bg-surface shadow-card ${className}`}>
      {children}
    </div>
  );
}

export function PageHeader({ title, subtitle, actions }) {
  return (
    <div className="mb-7 flex flex-col items-start justify-between gap-4 sm:flex-row sm:items-center">
      <div>
        <h1 className="font-display text-2xl font-bold tracking-tight text-ink sm:text-3xl">{title}</h1>
        {subtitle && <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
