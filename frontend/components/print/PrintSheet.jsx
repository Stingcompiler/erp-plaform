"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

/**
 * Renders its children into a print-only layer attached to <body>.
 *
 * Documents are previewed inside a Drawer, and a drawer is a scrolling,
 * overflow-hidden box — printing from inside it clips everything past the first
 * screenful. Portalling to body sidesteps that entirely: on paper the document
 * is a normal top-level block, not a fragment of a scroll container.
 *
 * The print rules live here rather than in global CSS on purpose. They hide
 * every other top-level element, which would break any other page that prints
 * its own way (/labels does). Scoping them to this component means the rules
 * simply do not exist unless a document is open.
 */
export default function PrintSheet({ children }) {
  const [mounted, setMounted] = useState(false);

  // Portals need a real DOM node, which the static export does not have during
  // prerender.
  useEffect(() => setMounted(true), []);
  if (!mounted) return null;

  return createPortal(
    <>
      <div className="print-sheet">{children}</div>
      <style jsx global>{`
        .print-sheet {
          display: none;
        }
        @media print {
          body > *:not(.print-sheet) {
            display: none !important;
          }
          .print-sheet {
            display: block;
            background: #fff;
            color: #000;
          }
          /* Keep a table row from being split across two pages. */
          .print-sheet tr,
          .print-sheet .avoid-break {
            page-break-inside: avoid;
          }
        }
        @page {
          margin: 14mm;
        }
      `}</style>
    </>,
    document.body,
  );
}
