"use client";

// The underline tab bar used by the sales, purchasing, returns and HR pages,
// with an optional attention badge per tab. `attentionKey` on a tab shows
// its count and marks it seen when the tab is opened — the same contract the
// sidebar uses, so a section can move from a page tab to a nav leaf (or
// back) without changing how its badge behaves.
//
// The tab a page opens on keeps its badge while it is on screen, so the
// number is actually seen; leaving that tab marks it seen.

const keysOf = (tab) =>
  Array.isArray(tab?.attentionKey) ? tab.attentionKey : tab?.attentionKey ? [tab.attentionKey] : [];

import { useEffect, useRef } from "react";

import AttentionBadge, { badgeFor } from "@/components/attention/AttentionBadge";
import { useAttention } from "@/components/attention/AttentionProvider";

export default function TabBar({ tabs, value, onChange, className = "" }) {
  const { counts, tones, markSeen } = useAttention();
  const previous = useRef(value);
  const tabsRef = useRef(tabs);
  tabsRef.current = tabs;
  useEffect(() => {
    if (previous.current !== value) {
      keysOf(tabsRef.current.find((tab) => tab.id === previous.current)).forEach(markSeen);
      previous.current = value;
    }
  }, [value, markSeen]);
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
              keysOf(tab).forEach(markSeen);
              onChange(tab.id);
            }}
            className={`tap -mb-px flex shrink-0 items-center gap-2 border-b-2 px-4 py-2 text-sm font-medium transition-colors ${
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
