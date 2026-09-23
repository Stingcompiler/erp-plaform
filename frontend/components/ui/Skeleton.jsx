"use client";

// Loading placeholders shaped like what is coming — rows for a table, lines
// for a panel — instead of the word "Loading…". The page keeps its shape
// while data arrives, so nothing jumps when it lands, and a slow connection
// reads as "almost there" rather than "stuck".
//
// Each one is a polite live region that says "Loading" to a screen reader;
// the grey bars themselves are hidden from it. The pulse stops for people
// who asked the system for reduced motion.

import { useI18n } from "../../app/providers/I18nProvider";
import { Card } from "@/components/ui/kit";

// Varied widths so the placeholder looks like text, not a barcode.
const WIDTHS = ["w-11/12", "w-4/5", "w-2/3", "w-3/4", "w-1/2", "w-5/6"];

function Bar({ className = "" }) {
  return <span aria-hidden="true" className={`block h-3 rounded bg-line motion-safe:animate-pulse ${className}`} />;
}

function Status({ className = "", children }) {
  const { t } = useI18n();
  return (
    <div role="status" aria-live="polite" className={className}>
      <span className="sr-only">{t("common.loading")}</span>
      {children}
    </div>
  );
}

// A few lines of text: panels, drawers, small sections.
export function SkeletonLines({ lines = 3, className = "" }) {
  return (
    <Status className={`space-y-3 py-2 ${className}`}>
      {Array.from({ length: lines }, (_, i) => <Bar key={i} className={WIDTHS[i % WIDTHS.length]} />)}
    </Status>
  );
}

// A list of rows, each a title line and a shorter detail line.
export function SkeletonRows({ rows = 4, className = "" }) {
  return (
    <Status className={`divide-y divide-line ${className}`}>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-4 px-4 py-4">
          <div className="min-w-0 flex-1 space-y-2">
            <Bar className={WIDTHS[i % WIDTHS.length]} />
            <Bar className="h-2.5 w-1/3" />
          </div>
          <Bar className="h-4 w-16 shrink-0" />
        </div>
      ))}
    </Status>
  );
}

// The same rows inside a card, for a section or a whole page that is loading.
export function SkeletonCard({ rows = 4, className = "" }) {
  return (
    <Card className={`overflow-hidden ${className}`}>
      <div className="border-b border-line px-4 py-4"><Bar className="h-4 w-40" /></div>
      <SkeletonRows rows={rows} />
    </Card>
  );
}

// Rows inside an existing <tbody>, one bar per column.
export function SkeletonTableRows({ cols, rows = 4 }) {
  const { t } = useI18n();
  return Array.from({ length: rows }, (_, r) => (
    <tr key={r} aria-hidden={r > 0 ? "true" : undefined}>
      {Array.from({ length: cols }, (_, c) => (
        <td key={c} className="px-4 py-4">
          {r === 0 && c === 0 && <span className="sr-only" role="status">{t("common.loading")}</span>}
          <Bar className={c === 0 ? "w-3/4" : WIDTHS[(r + c) % WIDTHS.length]} />
        </td>
      ))}
    </tr>
  ));
}
