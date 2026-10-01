"use client";

// The moving parts of the app's navigation (lib/navMotion.js): the pill
// that slides to the active sidebar item, the phone drawer that slides in
// from the start edge, and the turn of a toggle's icon. Shared by the
// company workspace (components/AppShell.jsx) and the platform console
// (components/PlatformShell.jsx). Styles: "Navigation motion" in
// app/globals.css.

import { useCallback, useEffect, useLayoutEffect, useRef } from "react";
import { X } from "lucide-react";

import { EASE_CSS } from "@/lib/motion";
import { ICON_TURN, NAV_MOTION, indicatorKeyframes, indicatorTransform } from "@/lib/navMotion";
import { usePresence } from "@/lib/usePresence";
import { isPrinting, prefersReducedMotion } from "@/lib/useReducedMotionSafe";

const useIsoLayoutEffect = typeof window === "undefined" ? useEffect : useLayoutEffect;

const canAnimate = (el) =>
  !!el && typeof el.animate === "function" && !prefersReducedMotion() && !isPrinting();

// The visible item marked as the current page. One inside a folded group
// does not count: the group shows its own dot, and the pill waits until the
// group opens.
function activeItem(list) {
  for (const item of list.querySelectorAll('[aria-current="page"]')) {
    if (!item.closest('.nav-collapse[data-open="false"]')) return item;
  }
  return null;
}

// One pill per list, measured from the active item and moved with a
// transform: on a route change it slides (a Web Animation with no fill, so
// the item is clickable at once and nothing is left behind); when the list
// changes height (a group opening, fonts arriving) it follows without a
// slide. Until it is placed the active item draws its own tint, so a page
// without JavaScript motion still shows where it is.
export function useNavIndicator(pathname, armed = true) {
  const listRef = useRef(null);
  const indicatorRef = useRef(null);
  const lastY = useRef(null);
  const running = useRef(null);

  const place = useCallback((slide) => {
    const list = listRef.current;
    const pill = indicatorRef.current;
    if (!list || !pill) return;
    const target = activeItem(list);
    if (!target) {
      pill.dataset.state = "off";
      lastY.current = null;
      return;
    }
    const y = target.offsetTop;
    const from = lastY.current;
    lastY.current = y;
    if (from === y && pill.dataset.state === "on") return;
    running.current?.cancel();
    running.current = null;
    pill.style.height = `${target.offsetHeight}px`;
    pill.style.transform = indicatorTransform(y);
    if (pill.dataset.state !== "on") {
      // First placement (or back from a folded group): appear in place.
      pill.dataset.state = "on";
      list.dataset.indicator = "on";
      return;
    }
    const frames = slide ? indicatorKeyframes(from, y) : null;
    if (frames && canAnimate(pill)) {
      running.current = pill.animate(frames, { duration: NAV_MOTION.indicator, easing: EASE_CSS });
    }
  }, []);

  // A route change slides the pill (the layout effect runs after the items'
  // aria-current is in the DOM, before paint).
  const firstRun = useRef(true);
  useIsoLayoutEffect(() => {
    place(!firstRun.current);
    firstRun.current = false;
  }, [pathname, place]);

  useEffect(() => {
    const list = listRef.current;
    if (!list || typeof ResizeObserver !== "function") return undefined;
    const observer = new ResizeObserver(() => place(false));
    observer.observe(list);
    return () => observer.disconnect();
  }, [place]);

  // Transitions (the pill fading in, groups folding) switch on two frames
  // after the list has its first real layout — `armed`, e.g. once the saved
  // open groups are restored — so nothing animates on page load.
  useEffect(() => {
    const list = listRef.current;
    if (!armed || !list || "navReady" in list.dataset) return undefined;
    let second = 0;
    const first = window.requestAnimationFrame(() => {
      second = window.requestAnimationFrame(() => { list.dataset.navReady = ""; });
    });
    return () => {
      window.cancelAnimationFrame(first);
      window.cancelAnimationFrame(second);
    };
  }, [armed]);

  return { listRef, indicatorRef };
}

export function NavIndicator({ ref }) {
  return (
    <span ref={ref} aria-hidden="true" data-state="off" className="nav-indicator">
      <span className="nav-indicator__bar" />
    </span>
  );
}

// The phone drawer: slides in from the start edge (the right in Arabic) over
// a fading backdrop; the backdrop, the close button and Escape close it.
// While it slides out it is inert — no clicks, no focus — and it unmounts
// when done (at once under reduced motion).
export function MobileDrawer({ open, onClose, closeLabel, children }) {
  const { mounted, state } = usePresence(open, NAV_MOTION.drawerOut);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event) => {
      if (event.key === "Escape" && !event.defaultPrevented) closeRef.current();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  if (!mounted) return null;
  return (
    <div className="shell-drawer fixed inset-0 z-40 overflow-hidden lg:hidden" data-state={state} inert={!open}>
      <div className="shell-drawer__scrim absolute inset-0 bg-black/50" onClick={() => closeRef.current()} />
      <aside className="shell-drawer__panel absolute inset-y-0 start-0 flex w-72 max-w-[85%] flex-col bg-sidebar shadow-xl">
        <button
          onClick={() => closeRef.current()}
          aria-label={closeLabel}
          className="tap absolute end-3 top-4 grid h-9 w-9 place-items-center rounded-control text-sidebarText/70 hover:bg-white/10"
        >
          <X size={18} />
        </button>
        {children}
      </aside>
    </div>
  );
}

// Turns a toggle's icon in (ICON_TURN) — called from the click, so it plays
// once per press and never on a page load.
export function turnIcon(el) {
  if (!canAnimate(el)) return;
  el.animate(ICON_TURN, { duration: NAV_MOTION.iconTurn, easing: EASE_CSS });
}
