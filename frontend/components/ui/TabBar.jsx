"use client";

// The underline tab bar used by the sales, purchasing, returns and HR pages,
// with an optional attention badge per tab. `attentionKey` on a tab shows
// its count and marks it seen when the tab is opened — the same contract the
// sidebar uses, so a section can move from a page tab to a nav leaf (or
// back) without changing how its badge behaves.
//
// The tab a page opens on keeps its badge while it is on screen, so the
// number is actually seen; leaving that tab marks it seen.
//
// The active tab's tint and underline are shared elements of the bar
// (framer-motion layoutId, components/ui/TabIndicator.jsx) that slide to the
// tab clicked, so the eye follows the change instead of hunting for the new
// active tab. The click is not held: the page switches at once and the
// indicator catches up in ~200 ms. Under reduced motion it jumps. The
// animation code loads after first paint; until then the indicator is
// static.

const keysOf = (tab) =>
  Array.isArray(tab?.attentionKey) ? tab.attentionKey : tab?.attentionKey ? [tab.attentionKey] : [];

import { useEffect, useId, useRef, useState } from "react";

import AttentionBadge, { badgeFor } from "@/components/attention/AttentionBadge";
import { useAttention } from "@/components/attention/AttentionProvider";
import { SPRING } from "@/lib/motion";
import { useReducedMotionSafe } from "@/lib/useReducedMotionSafe";

const TINT = "pointer-events-none absolute inset-x-0.5 inset-y-1 bg-accent/10";
const LINE = "pointer-events-none absolute inset-x-0 -bottom-0.5 h-0.5 bg-accent";

function StaticIndicator({ tintClass, lineClass }) {
  return (
    <>
      <span aria-hidden="true" className={tintClass} style={{ borderRadius: 10 }} />
      <span aria-hidden="true" className={lineClass} />
    </>
  );
}

// The sliding indicator, fetched once per page load when the browser is
// idle (a plain import(): next/dynamic would list the chunk as a script
// of the page and it would be parsed before first paint after all).
let sliding = null;
function whenIdle(run) {
  if (typeof window.requestIdleCallback === "function") {
    const id = window.requestIdleCallback(run, { timeout: 2000 });
    return () => window.cancelIdleCallback(id);
  }
  const id = window.setTimeout(run, 600);
  return () => window.clearTimeout(id);
}
function useSlidingIndicator() {
  const [Indicator, setIndicator] = useState(() => sliding || StaticIndicator);
  useEffect(() => {
    if (sliding) return undefined;
    let live = true;
    const cancel = whenIdle(() => {
      import("@/components/ui/TabIndicator")
        .then((module) => {
          sliding = module.default;
          if (live) setIndicator(() => sliding);
        })
        .catch(() => { /* offline without the chunk: the static one stays */ });
    });
    return () => { live = false; cancel(); };
  }, []);
  return Indicator;
}

export default function TabBar({ tabs, value, onChange, className = "" }) {
  const { counts, tones, markSeen } = useAttention();
  // One indicator per bar: two bars on a page must not trade theirs.
  const indicator = useId();
  const reduced = useReducedMotionSafe();
  const slide = reduced ? { duration: 0 } : SPRING;
  const TabIndicator = useSlidingIndicator();
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
            className={`tap relative -mb-px flex shrink-0 items-center gap-2 border-b-2 border-transparent px-4 py-2 text-sm font-medium transition-colors ${
              active ? "text-ink" : "text-muted hover:text-ink"
            }`}
          >
            {active && <TabIndicator id={indicator} transition={slide} tintClass={TINT} lineClass={LINE} />}
            <span className="relative">{tab.label}</span>
            <AttentionBadge count={badge.count} tone={badge.tone} className="relative" />
          </button>
        );
      })}
    </div>
  );
}
