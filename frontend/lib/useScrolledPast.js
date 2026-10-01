"use client";

import { useEffect, useState } from "react";

import { SCROLLED_AT, scrolledPast } from "./navMotion";

// Whether the window is scrolled past the top — a header then shows that
// content runs under it. One passive listener, read once per frame, and a
// re-render only when the answer flips. False on the server and first
// paint, so a public header renders as it is and changes only once read.
export function useScrolledPast(threshold = SCROLLED_AT) {
  const [past, setPast] = useState(false);
  useEffect(() => {
    let frame = 0;
    const read = () => {
      frame = 0;
      setPast(scrolledPast(window.scrollY, threshold));
    };
    const onScroll = () => {
      if (!frame) frame = window.requestAnimationFrame(read);
    };
    read();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, [threshold]);
  return past;
}
