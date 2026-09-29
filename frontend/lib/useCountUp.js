"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";

import { figureChars, splitFigure } from "./figureFit";
import { canCount, countUpDuration, easeOutCubic, interpolateFigure, parseFigure } from "./motion";
import { isPrinting, useReducedMotionSafe } from "./useReducedMotionSafe";

const useIsoLayoutEffect = typeof window === "undefined" ? useEffect : useLayoutEffect;

// A headline figure that counts to its value: from zero when it first
// appears, from what was on screen when it changes (a new report period).
//
// The final text is always in the layout — it sizes the card and is what a
// screen reader and a printer get — and the count is drawn over it
// (`overlay`), so counting never changes a card's width or height. The
// count writes straight to one text node per frame: no React render per
// frame, which is what keeps a dashboard of twelve counting cards smooth on
// a slow phone.
//
// Returns { counting, overlay, numberRef }: while `counting`, render
// `overlay` (the starting text) in an element whose number part carries
// `numberRef`.
export function useCountUp(value, enabled = true) {
  const reduced = useReducedMotionSafe();
  const [overlay, setOverlay] = useState(null);
  const shown = useRef(null);
  const frame = useRef(0);
  const numberRef = useRef(null);

  useIsoLayoutEffect(() => {
    const from = shown.current;
    cancelAnimationFrame(frame.current);
    const text = value === null || value === undefined ? "" : String(value);
    if (!enabled || reduced || isPrinting() || !canCount(from, text, figureChars)) {
      shown.current = text;
      setOverlay(null);
      return undefined;
    }
    const target = parseFigure(text);
    const origin = from === null ? 0 : parseFigure(from).number;
    const duration = countUpDuration(origin, target.number);
    const first = interpolateFigure(from, text, 0);
    shown.current = first;
    setOverlay(first);
    const started = performance.now();
    const tick = (now) => {
      const progress = Math.min(1, (now - started) / duration);
      const current = interpolateFigure(from, text, easeOutCubic(progress));
      shown.current = current;
      const node = numberRef.current?.firstChild;
      if (node) node.nodeValue = splitFigure(current)?.[0] ?? current;
      if (progress < 1) frame.current = requestAnimationFrame(tick);
      else setOverlay(null);
    };
    frame.current = requestAnimationFrame(tick);
    return undefined;
  }, [value, enabled, reduced]);

  useEffect(() => () => cancelAnimationFrame(frame.current), []);

  // Printing mid-count: the final text is already underneath; drop the
  // overlay (the print stylesheet hides it too).
  useEffect(() => {
    if (!overlay) return undefined;
    const done = () => {
      cancelAnimationFrame(frame.current);
      shown.current = value === null || value === undefined ? "" : String(value);
      setOverlay(null);
    };
    window.addEventListener("beforeprint", done);
    return () => window.removeEventListener("beforeprint", done);
  }, [overlay, value]);

  return { counting: overlay !== null, overlay, numberRef };
}
