"use client";

import { useEffect, useState } from "react";

import { ringFraction, ringGeometry, ringOffset } from "@/lib/motion";
import { prefersReducedMotion } from "@/lib/useReducedMotionSafe";

const TONES = {
  accent: "stroke-accent",
  ok: "stroke-ok",
  warn: "stroke-warn",
  danger: "stroke-danger",
};

// A ring that fills to a real number: days left of a trial, spent of a
// budget, sent of an upload queue. It is a progressbar to assistive tech
// (aria-valuenow / -max / -valuetext), and the number is written in the
// middle — the arc is never the only way to read it.
//
// It fills from empty when it appears and moves when the value changes
// (a CSS transition on stroke-dashoffset, .progress-ring__arc); under
// reduced motion it is drawn at its value from the first frame.
export default function ProgressRing({
  value,
  max,
  size = 64,
  stroke = 6,
  tone = "accent",
  label,
  valueText,
  children,
  className = "",
}) {
  const { radius, circumference, center } = ringGeometry(size, stroke);
  const fraction = ringFraction(value, max);
  const [drawn, setDrawn] = useState(() => typeof window === "undefined" || prefersReducedMotion());
  useEffect(() => {
    if (drawn) return undefined;
    let inner = 0;
    const outer = requestAnimationFrame(() => { inner = requestAnimationFrame(() => setDrawn(true)); });
    return () => { cancelAnimationFrame(outer); cancelAnimationFrame(inner); };
  }, [drawn]);
  const now = Math.max(0, Math.min(Number(max) || 0, Number(value) || 0));
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={Number(max) || 0}
      aria-valuenow={now}
      aria-valuetext={valueText}
      className={`relative inline-grid shrink-0 place-items-center ${className}`}
      style={{ width: size, height: size }}
    >
      <svg
        className="progress-ring__svg absolute inset-0"
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        aria-hidden="true"
      >
        <circle cx={center} cy={center} r={radius} fill="none" strokeWidth={stroke} className="stroke-line" />
        <circle
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          strokeWidth={stroke}
          strokeLinecap={fraction > 0 ? "round" : "butt"}
          strokeDasharray={circumference}
          strokeDashoffset={ringOffset(drawn ? fraction : 0, circumference)}
          className={`progress-ring__arc ${TONES[tone] || TONES.accent}`}
          style={fraction > 0 ? undefined : { opacity: 0 }}
        />
      </svg>
      <div className="relative text-center leading-tight">{children}</div>
    </div>
  );
}
