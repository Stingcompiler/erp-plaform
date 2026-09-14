"use client";

// The underline tab bar used by the sales, purchasing, returns and HR pages,
// with an optional attention badge per tab. `attentionKey` on a tab shows
// its count and marks it seen when the tab is opened — the same contract the
// sidebar uses, so a section can move from a page tab to a nav leaf (or
// back) without changing how its badge behaves.

import AttentionBadge, { badgeFor } from "@/components/attention/AttentionBadge";
import { useAttention } from "@/components/attention/AttentionProvider";

export default function TabBar({ tabs, value, onChange, className = "" }) {
  const { counts, tones, markSeen } = useAttention();
  return (
    <div role="tablist" className={`mb-6 flex gap-1 overflow-x-auto border-b border-line ${className}`}>
      {tabs.map((tab) => {
        const badge = badgeFor(tab.attentionKey, counts, tones);
        const active = value === tab.id;
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => {
              const keys = Array.isArray(tab.attentionKey) ? tab.attentionKey : tab.attentionKey ? [tab.attentionKey] : [];
              keys.forEach(markSeen);
              onChange(tab.id);
            }}
            className={`-mb-px flex shrink-0 items-center gap-2 border-b-2 px-4 py-2 text-sm font-medium transition-colors ${
              active ? "border-accent text-ink" : "border-transparent text-muted hover:text-ink"
            }`}
          >
            {tab.label}
            <AttentionBadge count={badge.count} tone={badge.tone} />
          </button>
        );
      })}
    </div>
  );
}
