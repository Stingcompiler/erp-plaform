"use client";

import { motion } from "framer-motion";

// The sliding version of the active tab's tint and underline
// (components/ui/TabBar.jsx). Imported by the bar when the browser is idle
// after first paint, so framer-motion is never part of a page's initial
// script — the till included. Until it arrives the bar draws the same two
// spans without motion.
export default function TabIndicator({ id, transition, tintClass, lineClass }) {
  return (
    <>
      <motion.span
        layoutId={`${id}-tint`}
        transition={transition}
        aria-hidden="true"
        className={tintClass}
        style={{ borderRadius: 10 }}
      />
      <motion.span
        layoutId={`${id}-line`}
        transition={transition}
        aria-hidden="true"
        className={lineClass}
      />
    </>
  );
}
