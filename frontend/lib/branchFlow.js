// Geometry of the "branches → head office" diagram on the public site
// (components/marketing/BranchFlow.jsx). It echoes the logo
// (lib/brandMark.js): branches above, converging into a hub of four module
// tiles in the brand's checkerboard. Pure, so it is tested in node.
//
// Drawn on a VIEW.width × VIEW.height grid. The branches read in the
// page's direction: in Arabic the first branch is on the right, and the
// first module tile is the top-right one.

export const VIEW = { width: 360, height: 262 };

const NODE = { y: 32, width: 104, height: 36 };
const NODE_XS = [62, 180, 298];
const TILE = { width: 84, height: 38, gap: 6, radius: 8 };
const HUB = { cx: 180, top: 152 };

const r1 = (n) => Math.round(n * 10) / 10;

// Positions in reading order: index 0 is where a reader starts.
function inReadingOrder(xs, dir) {
  return dir === "rtl" ? [...xs].reverse() : xs;
}

export function branchFlowLayout(dir = "ltr", branchCount = 3) {
  const count = Math.max(1, Math.min(branchCount, NODE_XS.length));
  const xs = inReadingOrder(NODE_XS, dir).slice(0, count);

  const hubWidth = TILE.width * 2 + TILE.gap;
  const hubHeight = TILE.height * 2 + TILE.gap;
  const left = HUB.cx - hubWidth / 2;
  const columns = inReadingOrder([left, left + TILE.width + TILE.gap], dir);
  const rows = [HUB.top, HUB.top + TILE.height + TILE.gap];
  // Checkerboard like the logo: solid teal on the diagonal from the
  // reading start, pale on the other two.
  const tiles = [
    [columns[0], rows[0], "solid"], [columns[1], rows[0], "pale"],
    [columns[0], rows[1], "pale"], [columns[1], rows[1], "solid"],
  ].map(([x, y, tone]) => ({
    x, y, width: TILE.width, height: TILE.height, rx: TILE.radius, tone,
    labelX: x + TILE.width / 2, labelY: y + TILE.height / 2,
  }));

  // Each branch lands on the hub's top edge: the outer ones over the outer
  // tiles' centres, the middle one on the hub's centre line.
  const landing = (x) => {
    if (x < HUB.cx) return left + TILE.width / 2;
    if (x > HUB.cx) return left + hubWidth - TILE.width / 2;
    return HUB.cx;
  };
  const startY = NODE.y + NODE.height / 2;
  const midY = r1((startY + HUB.top) / 2);
  const branches = xs.map((x) => {
    const to = landing(x);
    return {
      x,
      y: NODE.y,
      width: NODE.width,
      height: NODE.height,
      path: `M${x} ${startY} C${x} ${midY} ${to} ${midY} ${to} ${HUB.top}`,
    };
  });

  return {
    view: VIEW,
    branches,
    tiles,
    hub: { x: left, y: HUB.top, width: hubWidth, height: hubHeight },
    caption: { x: HUB.cx, y: HUB.top + hubHeight + 22 },
  };
}

// The dots' timetable (seconds): the paths draw first, then one dot per
// branch sets off, a beat apart, and each lap takes `lap`.
export const FLOW_TIMING = { drawMs: 700, drawStepMs: 120, firstDot: 0.9, dotStep: 0.8, lap: 2.4 };

export function dotBegin(index) {
  return `${Math.round((FLOW_TIMING.firstDot + FLOW_TIMING.dotStep * index) * 100) / 100}s`;
}
