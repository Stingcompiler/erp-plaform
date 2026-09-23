"use client";

// Gives every cell of a `table.stack-sm` a data-label with its column
// heading, so the phone layout in globals.css can show "Price  420.00"
// instead of a bare number. Tables re-render all the time (paging,
// filters, live data), so this watches the page and relabels on change
// rather than asking each of the 20-odd list tables to pass labels down.

import { useEffect } from "react";

function label(table) {
  const heads = [...table.querySelectorAll("thead th")].map((th) => th.textContent.trim());
  if (!heads.length) return;
  table.querySelectorAll("tbody tr").forEach((tr) => {
    let col = 0;
    for (const td of tr.children) {
      if (td.tagName !== "TD") continue;
      const span = Number(td.getAttribute("colspan") || 1);
      if (span === 1) {
        const text = heads[col] ?? "";
        if (td.getAttribute("data-label") !== text) td.setAttribute("data-label", text);
      }
      col += span;
    }
  });
}

export default function TableCardLabels() {
  useEffect(() => {
    let frame = 0;
    const run = () => {
      frame = 0;
      document.querySelectorAll("table.stack-sm").forEach(label);
    };
    const schedule = () => { if (!frame) frame = requestAnimationFrame(run); };
    schedule();
    const observer = new MutationObserver(schedule);
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
    return () => { observer.disconnect(); if (frame) cancelAnimationFrame(frame); };
  }, []);
  return null;
}
