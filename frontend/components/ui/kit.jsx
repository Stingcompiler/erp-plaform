"use client";

import { forwardRef } from "react";

export function Button({ variant = "primary", className = "", ...props }) {
  const base =
    "inline-flex items-center justify-center gap-2 rounded-control px-3.5 py-2 text-sm font-medium transition-colors disabled:opacity-50 disabled:pointer-events-none";
  const variants = {
    primary: "bg-accent text-white hover:bg-accent-strong",
    ghost: "text-muted hover:bg-paper hover:text-ink",
    outline: "border border-line text-ink hover:bg-paper",
    danger: "bg-danger text-white hover:opacity-90",
  };
  return <button className={`${base} ${variants[variant]} ${className}`} {...props} />;
}

export function Field({ label, hint, children }) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm font-medium text-ink">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-muted">{hint}</span>}
    </label>
  );
}

const controlClass =
  "w-full rounded-control border border-line bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-accent";

// forwardRef so callers can focus the field programmatically — the barcode
// scanner relies on refocusing after every scan.
export const Input = forwardRef(function Input({ className = "", ...props }, ref) {
  return <input ref={ref} className={`${controlClass} ${className}`} {...props} />;
});

export function Select({ className = "", children, ...props }) {
  return (
    <select className={`${controlClass} ${className}`} {...props}>
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
    <div className={`rounded-card border border-line bg-surface shadow-card ${className}`}>
      {children}
    </div>
  );
}

export function PageHeader({ title, subtitle, actions }) {
  return (
    <div className="mb-6 flex items-start justify-between gap-4">
      <div>
        <h1 className="font-display text-2xl font-bold text-ink">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}
