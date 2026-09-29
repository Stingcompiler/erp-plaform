"use client";

// Three branches feeding one head office: the logo's idea (branches
// converging into a hub of module tiles) drawn as a diagram. Geometry in
// lib/branchFlow.js.
//
// In the HTML it is a finished, static drawing. With `animate`, after
// hydration and only when motion is welcome, the paths draw in as the
// diagram scrolls into view, then a dot runs down each branch to the hub
// in a loop (SVG animateMotion) that is paused whenever the diagram is off
// screen. Under reduced motion the dots are never added.
import { useEffect, useLayoutEffect, useRef, useState } from "react";

import { useI18n } from "@/app/providers/I18nProvider";
import { FLOW_TIMING, branchFlowLayout, dotBegin } from "@/lib/branchFlow";
import { useReducedMotionSafe } from "@/lib/useReducedMotionSafe";

const useIsoLayoutEffect = typeof window === "undefined" ? useEffect : useLayoutEffect;

// The tile colours are the logo's (--brand / --brand-node), the same in
// both themes; the text on the pale tile is the dark teal of the mark.
const TILE_FILL = { solid: "rgb(var(--brand))", pale: "rgb(var(--brand-node))" };
const TILE_TEXT = { solid: "rgb(var(--brand-ink))", pale: "#0b5a61" };

export default function BranchFlow({ animate = true, className = "" }) {
  const { t, dir } = useI18n();
  const reduce = useReducedMotionSafe();
  const live = animate && !reduce;
  const svgRef = useRef(null);
  const [drawState, setDrawState] = useState(null); // null | "armed" | "in"

  const names = t("home.flowBranches");
  const modules = t("home.flowModules");
  const branchNames = Array.isArray(names) ? names : [];
  const moduleNames = Array.isArray(modules) ? modules : [];
  const layout = branchFlowLayout(dir, branchNames.length || 3);

  // Hold the dots' clock until the diagram is on screen, and hold it again
  // whenever it leaves. Layout effect: the clock is stopped before the
  // dots' first frame is painted.
  useIsoLayoutEffect(() => {
    const svg = svgRef.current;
    if (!live || !svg || typeof svg.pauseAnimations !== "function") return undefined;
    svg.pauseAnimations();
    if (typeof IntersectionObserver === "undefined") return undefined;
    const below = svg.getBoundingClientRect().top > window.innerHeight;
    if (below) setDrawState("armed");
    let started = false;
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        if (!started) {
          started = true;
          setDrawState((state) => (state === "armed" ? "in" : state));
          svg.setCurrentTime(0);
        }
        svg.unpauseAnimations();
      } else {
        svg.pauseAnimations();
      }
    });
    observer.observe(svg);
    return () => {
      observer.disconnect();
      setDrawState(null);
    };
  }, [live]);

  const { view, branches, tiles, hub, caption } = layout;
  const label = t("home.flowLabel");

  return (
    <svg
      ref={svgRef}
      role="img"
      aria-label={label}
      viewBox={`0 0 ${view.width} ${view.height}`}
      width={view.width}
      height={view.height}
      className={`branch-flow mx-auto block h-auto w-full max-w-md font-display ${className}`}
      data-draw-state={drawState || undefined}
    >
      {/* Head-office glow: breathes as the dots arrive. */}
      <rect
        x={hub.x - 6} y={hub.y - 6} width={hub.width + 12} height={hub.height + 12} rx="14"
        fill="none" strokeWidth="2" className="stroke-accent" opacity={live ? 0.15 : 0}
      >
        {live && (
          <animate attributeName="opacity" values="0.15;0.55;0.15" dur={`${FLOW_TIMING.lap}s`} begin={dotBegin(0)} repeatCount="indefinite" />
        )}
      </rect>

      {branches.map((branch, index) => (
        <path
          key={`path-${index}`}
          d={branch.path}
          pathLength="1"
          fill="none"
          strokeWidth="2"
          strokeLinecap="round"
          className="branch-flow__path stroke-accent/50"
          style={{ "--flow-delay": `${index * FLOW_TIMING.drawStepMs}ms`, "--flow-dur": `${FLOW_TIMING.drawMs}ms` }}
        />
      ))}

      {branches.map((branch, index) => (
        <g key={`node-${index}`}>
          <rect
            x={branch.x - branch.width / 2} y={branch.y} width={branch.width} height={branch.height} rx={branch.height / 2}
            className="fill-surface stroke-line" strokeWidth="1.5"
          />
          <circle cx={branch.x} cy={branch.y + branch.height} r="3.5" className="fill-accent" />
          <text
            x={branch.x} y={branch.y + branch.height / 2} textAnchor="middle" dominantBaseline="central"
            fontSize="14" fontWeight="600" className="fill-ink"
          >
            {branchNames[index]}
          </text>
        </g>
      ))}

      {tiles.map((tile, index) => (
        <g key={`tile-${index}`}>
          <rect x={tile.x} y={tile.y} width={tile.width} height={tile.height} rx={tile.rx} fill={TILE_FILL[tile.tone]} />
          <text
            x={tile.labelX} y={tile.labelY} textAnchor="middle" dominantBaseline="central"
            fontSize="13" fontWeight="600" fill={TILE_TEXT[tile.tone]}
          >
            {moduleNames[index]}
          </text>
        </g>
      ))}

      <text x={caption.x} y={caption.y} textAnchor="middle" dominantBaseline="central" fontSize="12" className="fill-muted">
        {t("home.flowHub")}
      </text>

      {live && branches.map((branch, index) => (
        <circle key={`dot-${index}`} r="4" cx="0" cy="0" opacity="0" className="fill-accent">
          <animateMotion
            path={branch.path} dur={`${FLOW_TIMING.lap}s`} begin={dotBegin(index)} repeatCount="indefinite"
            calcMode="spline" keyPoints="0;1" keyTimes="0;1" keySplines="0.45 0 0.25 1"
          />
          <animate
            attributeName="opacity" values="0;1;1;0" keyTimes="0;0.12;0.85;1"
            dur={`${FLOW_TIMING.lap}s`} begin={dotBegin(index)} repeatCount="indefinite"
          />
        </circle>
      ))}
    </svg>
  );
}
