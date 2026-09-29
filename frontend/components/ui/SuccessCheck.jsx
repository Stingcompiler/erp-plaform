"use client";

import { useState } from "react";

import { prefersReducedMotion } from "@/lib/useReducedMotionSafe";

// A green disc with a tick drawn into it: "done" for a sale, an approved
// payment, an approved payroll. 350 ms, pure CSS (.success-check in
// globals.css), so it costs the till nothing and never holds a click or a
// scan — the screen around it is usable from the first frame. Under reduced
// motion the finished check is drawn at once.
//
// It plays once when it mounts; give it a new `key` to play it again.
export default function SuccessCheck({ size = 48, label, className = "" }) {
  const [animate] = useState(() => typeof window !== "undefined" && !prefersReducedMotion());
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : "true"}
      className={`success-check ${animate ? "success-check--animate" : ""} shrink-0 text-ok ${className}`}
    >
      <circle className="success-check__disc fill-ok/10" cx="24" cy="24" r="23" />
      <path
        className="success-check__tick"
        d="M15 24.5l6 6L33.5 18"
        fill="none"
        stroke="currentColor"
        strokeWidth="3.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        pathLength="1"
      />
    </svg>
  );
}
