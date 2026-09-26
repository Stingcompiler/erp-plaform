// The Vezano Pro logo mark ("blend C"): two branches converge into a hub of
// four module tiles, with a refresh-style sync arrow climbing the hub's right
// side — many branches, one system, kept in sync. design/brand/README.md explains it.
//
// One geometry for everything that draws it: components/brand/LogoMark.jsx
// (the UI), scripts/brand-icons.mjs (design/brand masters, then the favicon,
// PWA and Apple icons rasterised from them) and the Django directory page.
//
// Drawn on a 64×64 grid; branches and tiles are symmetric about x = 32. The
// sync arrow is concentric with the hub and sits on its right (a refresh
// arrow), not centred under it: centred, it read as a smile. Each tier is
// placed so its visual bounding box is centred (the thin arc carries little
// weight, so the full mark sits a touch low).
//
// Tiers, by rendered size:
//   full    ≥ 48px  branches, nodes, 4 tiles, sync arrow
//   medium  24–47   branches, nodes, 4 tiles (the arc would blur)
//   small   < 24    two thick branches and one solid hub square

// The tile teal: --brand in app/globals.css and the Django wordmark partial
// carry the same value; change them together.
export const BRAND_TEAL = "#0e7c86";
// Branch nodes, the two "module" tiles and the arc: a pale tint of the teal.
export const BRAND_NODE = "#a3e3e6";
export const BRAND_INK = "#ffffff";
export const MARK_LABEL = { ar: "فيزانو برو", en: "Vezano Pro" };

export const TIER_MIN = { full: 48, medium: 24 };
export function tierFor(size) {
  if (size >= TIER_MIN.full) return "full";
  if (size >= TIER_MIN.medium) return "medium";
  return "small";
}

const r2 = (n) => Math.round(n * 100) / 100;

function hubTiles(cx, cy, tile, gap, radius) {
  const half = tile + gap / 2;
  const x0 = cx - half;
  const x1 = cx + gap / 2;
  const y0 = cy - half;
  const y1 = cy + gap / 2;
  // Checkerboard: white top-left and bottom-right, pale the other two.
  return [
    [x0, y0, "ink"], [x1, y0, "node"], [x0, y1, "node"], [x1, y1, "ink"],
  ].map(([x, y, fill]) => ({
    tag: "rect", fill, attrs: { x: r2(x), y: r2(y), width: tile, height: tile, rx: radius },
  }));
}

function branches(cx, top, nodeX, nodeY, stroke, reach) {
  // Each branch runs from its node to the hub's top corner tile.
  return {
    tag: "path",
    stroke: "ink",
    attrs: {
      d: `M${nodeX} ${nodeY} L${r2(cx - reach)} ${r2(top)} M${64 - nodeX} ${nodeY} L${r2(cx + reach)} ${r2(top)}`,
      fill: "none", strokeWidth: stroke, strokeLinecap: "round", strokeLinejoin: "round",
    },
  };
}

function syncArc(cx, cy, radius, stroke, from = 115, to = -22, head = 4.2) {
  // Screen angles, clockwise with y down: 0° is right of the hub, 90° below
  // it, -90° above. The arc is a refresh arrow on the right of the hub: it
  // starts below the hub, a little left of centre, climbs the right side
  // (angle decreasing) and ends at the upper right, where the arrowhead
  // points along the direction of travel. One-sided on purpose: an arc
  // centred under the hub read as a smile (v1, design/brand/concepts).
  const pt = (deg) => [cx + radius * Math.cos((deg * Math.PI) / 180), cy + radius * Math.sin((deg * Math.PI) / 180)];
  const [sx, sy] = pt(from);
  const [ex, ey] = pt(to);
  const t = (to * Math.PI) / 180;
  // Direction of travel at the end (angle decreasing): (sin t, -cos t).
  const dir = [Math.sin(t), -Math.cos(t)];
  const back = [-dir[0], -dir[1]];
  const rot = (v, a) => [v[0] * Math.cos(a) - v[1] * Math.sin(a), v[0] * Math.sin(a) + v[1] * Math.cos(a)];
  const spread = (42 * Math.PI) / 180;
  const a1 = rot(back, spread);
  const a2 = rot(back, -spread);
  const common = { fill: "none", strokeWidth: stroke, strokeLinecap: "round", strokeLinejoin: "round" };
  const large = from - to > 180 ? 1 : 0;
  return [
    { tag: "path", stroke: "node", attrs: { d: `M${r2(sx)} ${r2(sy)} A${radius} ${radius} 0 ${large} 0 ${r2(ex)} ${r2(ey)}`, ...common } },
    {
      tag: "path",
      stroke: "node",
      attrs: {
        d: `M${r2(ex + a1[0] * head)} ${r2(ey + a1[1] * head)} L${r2(ex)} ${r2(ey)} L${r2(ex + a2[0] * head)} ${r2(ey + a2[1] * head)}`,
        ...common,
      },
    },
  ];
}

const TIERS = {
  full: () => {
    const cx = 32, cy = 39.5, tile = 7, gap = 1.4, half = tile + gap / 2;
    const nodeY = 14, nodeX = 15;
    return [
      branches(cx, cy - half, nodeX, nodeY, 4.5, 6),
      { tag: "circle", fill: "node", attrs: { cx: nodeX, cy: nodeY, r: 4.3 } },
      { tag: "circle", fill: "node", attrs: { cx: 64 - nodeX, cy: nodeY, r: 4.3 } },
      ...hubTiles(cx, cy, tile, gap, 1.6),
      ...syncArc(cx, cy, 14.5, 2.6, 115, -22, 4.2),
    ];
  },
  medium: () => {
    const cx = 32, cy = 43, tile = 7.2, gap = 1.6, half = tile + gap / 2;
    const nodeY = 18, nodeX = 15;
    return [
      branches(cx, cy - half, nodeX, nodeY, 5.2, 6.2),
      { tag: "circle", fill: "node", attrs: { cx: nodeX, cy: nodeY, r: 5 } },
      { tag: "circle", fill: "node", attrs: { cx: 64 - nodeX, cy: nodeY, r: 5 } },
      ...hubTiles(cx, cy, tile, gap, 1.8),
    ];
  },
  small: () => {
    const cx = 32, hub = 19, top = 33;
    return [
      branches(cx, top + 1, 16, 16, 8, 6.5),
      { tag: "rect", fill: "ink", attrs: { x: cx - hub / 2, y: top, width: hub, height: hub, rx: 3.5 } },
    ];
  },
};

/**
 * The elements of one tier, each with a colour role ("ink", "node") for
 * fill or stroke. `mono` turns every role black (thermal receipts).
 */
export function markElements(tier = "full") {
  return TIERS[tier]();
}

const COLOURS = { ink: BRAND_INK, node: BRAND_NODE };
const MONO = { ink: "#000", node: "#000" };
const kebab = (k) => k.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`);

/**
 * The mark as a standalone SVG string (masters, icons, server templates).
 *   tier   "full" | "medium" | "small"
 *   shape  "rounded" tile (transparent corners) or "square" (full-bleed:
 *          maskable and Apple icons)
 *   inset  glyph scale inside the tile (maskable keeps it in the safe zone)
 *   mono   black shapes, no tile
 */
export function markSvg({ tier = "full", shape = "rounded", inset = 1, mono = false, size = 64, title } = {}) {
  const colours = mono ? MONO : COLOURS;
  const tile = mono
    ? ""
    : `<rect width="64" height="64"${shape === "square" ? "" : ' rx="14"'} fill="${BRAND_TEAL}"/>`;
  const body = markElements(tier).map(({ tag, attrs, fill, stroke }) => {
    const all = { ...attrs };
    if (fill) all.fill = colours[fill];
    if (stroke) all.stroke = colours[stroke];
    const text = Object.entries(all).map(([k, v]) => `${kebab(k)}="${v}"`).join(" ");
    return `<${tag} ${text}/>`;
  }).join("");
  const transform = inset === 1 ? "" : ` transform="translate(32 32) scale(${inset}) translate(-32 -32)"`;
  const label = title ? `<title>${title}</title>` : "";
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="${size}" height="${size}">` +
    `${label}${tile}<g${transform}>${body}</g></svg>`
  );
}
