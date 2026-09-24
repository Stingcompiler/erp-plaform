"use client";

import { useEffect, useRef, useState } from "react";
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
 * its own way. Scoping them to this component means the rules simply do not
 * exist unless a document is open.
 *
 * Every page has zero margin. The browser prints its own header and footer
 * (page title, the site address, the date, "1/2") inside the page margin, so a
 * receipt came out with the server's URL on it unless the cashier knew to
 * untick "Headers and footers". With no margin there is nowhere to print them;
 * the white space around the document is padding on the sheet instead, cloned
 * onto every page so a two-page invoice keeps its margins too.
 */
export const PAPERS = {
  a4: { size: "A4", width: "210mm", pad: "12mm 14mm" },
  a5: { size: "A5", width: "148mm", pad: "8mm 9mm" },
  // Roll printers: the paper is 80 / 58 mm, the head prints 72 / 48 mm of it.
  // The page is exactly as long as the receipt (measured below), so the
  // printer feeds and cuts once instead of spitting an A4's worth of roll.
  "80mm": { roll: true, width: "80mm", pad: "0" },
  "58mm": { roll: true, width: "58mm", pad: "0" },
  // Barcode labels: the common A4 sheet of 24 (3 x 8, 70 x 37 mm, no gaps)
  // and the two usual label-printer rolls, one label per page.
  "label-a4": { size: "A4", width: "210mm", pad: "0.5mm 0 0" },
  "label-40x30": { size: "40mm 30mm", width: "40mm", pad: "0" },
  "label-50x25": { size: "50mm 25mm", width: "50mm", pad: "0" },
};

// Paper fed past the last line so the cutter does not clip it.
const ROLL_FEED_MM = 8;
const PX_PER_MM = 96 / 25.4;

export default function PrintSheet({ children, paper = "a4", title }) {
  const [mounted, setMounted] = useState(false);
  const [rollMm, setRollMm] = useState(null);
  const ref = useRef(null);
  const spec = PAPERS[paper] || PAPERS.a4;

  // Portals need a real DOM node, which the static export does not have during
  // prerender.
  useEffect(() => setMounted(true), []);

  // A roll page is as long as its content. The sheet is laid out off-screen at
  // the roll's width, so its height here is its height on paper.
  useEffect(() => {
    if (!mounted || !spec.roll || !ref.current) return undefined;
    const node = ref.current;
    const measure = () => setRollMm(Math.ceil(node.scrollHeight / PX_PER_MM) + ROLL_FEED_MM);
    measure();
    if (typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, [mounted, spec.roll, paper]);

  // The page title names the PDF when "Save as PDF" is chosen; the document
  // number is a better file name than the app's title.
  useEffect(() => {
    if (!title) return undefined;
    let previous = null;
    const before = () => { previous = document.title; document.title = title; };
    const after = () => { if (previous !== null) document.title = previous; previous = null; };
    window.addEventListener("beforeprint", before);
    window.addEventListener("afterprint", after);
    return () => {
      after();
      window.removeEventListener("beforeprint", before);
      window.removeEventListener("afterprint", after);
    };
  }, [title]);

  if (!mounted) return null;

  const size = spec.roll ? `${spec.width} ${rollMm || 200}mm` : spec.size;

  return createPortal(
    <>
      <div className="print-sheet" ref={ref} dir={document.documentElement.dir || undefined}>
        {children}
      </div>
      <style jsx global>{`
        .print-sheet {
          position: fixed;
          top: 0;
          left: -10000px;
          visibility: hidden;
          pointer-events: none;
          box-sizing: border-box;
          width: ${spec.width};
          padding: ${spec.pad};
          background: #fff;
          color: #000;
        }
        @media print {
          html,
          body {
            margin: 0 !important;
            padding: 0 !important;
            background: #fff !important;
            min-height: 0 !important;
          }
          body > *:not(.print-sheet) {
            display: none !important;
          }
          .print-sheet {
            position: static;
            visibility: visible;
            width: auto;
            -webkit-box-decoration-break: clone;
            box-decoration-break: clone;
            -webkit-print-color-adjust: exact;
            print-color-adjust: exact;
          }
          /* Keep a table row from being split across two pages. */
          .print-sheet tr,
          .print-sheet .avoid-break {
            page-break-inside: avoid;
          }
        }
        @page {
          size: ${size};
          margin: 0;
        }
      `}</style>
    </>,
    document.body,
  );
}
