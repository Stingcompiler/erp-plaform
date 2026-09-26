"use client";

import { createElement } from "react";

import { useI18n } from "@/app/providers/I18nProvider";
import { MARK_LABEL, markElements, tierFor } from "@/lib/brandMark";

// The Vezano Pro logo mark on its teal tile (geometry and tiers in
// lib/brandMark.js). The tile is the brand teal in both themes (--brand), so
// the logo does not change colour with the page.
//
//   size        rendered px (square); picks the tier: full ≥ 48, medium
//               24–47, small < 24
//   tier        force a tier ("full" | "medium" | "small"); `small` is
//               shorthand for tier="small" (favicon sizes)
//   mono        black shapes, no tile — thermal receipts
//   decorative  hide it from screen readers when the name is written next
//               to it (the Wordmark), so the name is not read twice
const ROLE = { ink: "rgb(var(--brand-ink))", node: "rgb(var(--brand-node))" };

export default function LogoMark({ size = 32, tier, small = false, mono = false, decorative = false, className = "" }) {
  const { language } = useI18n();
  const elements = markElements(tier || (small ? "small" : tierFor(size)));
  const colour = (role) => (mono ? "#000" : ROLE[role]);
  const a11y = decorative
    ? { "aria-hidden": true }
    : { role: "img", "aria-label": MARK_LABEL[language === "en" ? "en" : "ar"] };
  return (
    <svg viewBox="0 0 64 64" width={size} height={size} className={`shrink-0 ${className}`} {...a11y}>
      {!mono && <rect width="64" height="64" rx="14" style={{ fill: "rgb(var(--brand))" }} />}
      {elements.map(({ tag, attrs, fill, stroke }, i) =>
        createElement(tag, {
          key: i,
          ...attrs,
          style: { ...(fill ? { fill: colour(fill) } : {}), ...(stroke ? { stroke: colour(stroke) } : {}) },
        }),
      )}
    </svg>
  );
}
