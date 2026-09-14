"use client";

// The count that sits on a tab: teal for something new waiting for an
// ordinary action, amber for money waiting for approval, red for a risk.
// Renders nothing at zero so the nav stays quiet when nothing needs anyone.

const TONE_CLASS = {
  info: "bg-accent text-white",
  warn: "bg-warn text-white",
  danger: "bg-danger text-white",
};
const RANK = { info: 0, warn: 1, danger: 2 };

// Sum several keys (a nav group) and keep the most urgent tone among them.
export function badgeFor(keys, counts, tones) {
  const list = Array.isArray(keys) ? keys : keys ? [keys] : [];
  let count = 0;
  let tone = "info";
  for (const key of list) {
    const n = counts?.[key] || 0;
    if (!n) continue;
    count += n;
    const t = tones?.[key] || "info";
    if (RANK[t] > RANK[tone]) tone = t;
  }
  return { count, tone };
}

export default function AttentionBadge({ count, tone = "info", className = "" }) {
  if (!count) return null;
  return (
    <span
      aria-label={String(count)}
      className={`tabular inline-flex h-5 min-w-5 shrink-0 items-center justify-center rounded-full px-1.5 font-mono text-[11px] font-semibold leading-none ${TONE_CLASS[tone] || TONE_CLASS.info} ${className}`}
    >
      {count > 99 ? "99+" : count}
    </span>
  );
}
