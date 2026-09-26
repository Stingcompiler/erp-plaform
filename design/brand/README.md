# Vezano Pro brand — «فيزانو برو»

The product is **«فيزانو برو»** in Arabic and **Vezano Pro** in English. The
domain stays `vezano.app`.

## The mark

"Blend C": two **branches** (the nodes at the top) converge into a **hub of
four module tiles** — sales, inventory, people, finance in one system — and a
**sync arc** with an arrowhead runs around the hub: every branch, one system,
kept in step even when the network drops.

The geometry lives in one place, `frontend/lib/brandMark.js`, on a 64×64 grid,
symmetric about the vertical axis, with the sync arc concentric with the hub.
The in-app component (`frontend/components/brand/LogoMark.jsx`), these masters
and every app icon are drawn from it.

### Size tiers

| Tier   | Rendered size | What it keeps                                   | Master            |
|--------|---------------|-------------------------------------------------|-------------------|
| Full   | 48 px and up  | branches, nodes, 4 tiles, sync arc              | `mark-full.svg`   |
| Medium | 24–47 px      | branches, nodes, 4 tiles (no arc)               | `mark-medium.svg` |
| Small  | under 24 px   | two thick branches and one solid hub square     | `mark-small.svg`  |

Minimum sizes: full 48 px, medium 24 px, small 16 px (favicon). The 512, 192
and Apple (180) icons use the full mark; favicons (16/32) use the small tier.

Other masters:

- `mark-maskable.svg` — full-bleed teal, the full mark scaled to 80% so it sits
  inside the maskable safe zone (the central circle, radius 40%).
- `mark-apple.svg` — full-bleed, no transparency (iOS rounds the corners).
- `mark-mono.svg` — monochrome black, medium tier, solid shapes on white: for
  thermal receipts and one-colour printing.
- `lockup-{ar,en}-{light,dark}.svg` — mark + wordmark. Arabic: the mark on the
  right of «فيزانو برو»; English: the mark on the left of "Vezano Pro". Dark
  lockups are for dark surfaces. `png/` holds exports of every master.
- `concepts/` — the explored marks, for the record: 1 branches converge,
  2 modules, 3 V with sync arrows, 4 Arabic ف, blend A branches + modules,
  blend B branches + sync. Blend C (branches + modules + sync) was chosen.

### Clear space

Keep clear space around the tile of at least **¼ of the tile's width** (16
units on the 64 grid). In a lockup the gap between tile and wordmark is 20
units (for a 64 px tile, 20 px).

## Colours

| Role                                   | Hex       |
|----------------------------------------|-----------|
| Brand teal — tile, light-theme accent  | `#0e7c86` |
| Pale teal — branch nodes, 2 tiles, arc | `#a3e3e6` |
| White — branches, 2 tiles              | `#ffffff` |
| Dark-theme accent («برو» on dark)      | `#37b0b8` |
| Ink (wordmark on light)                | `#12253b` |
| Paper (wordmark on dark)               | `#f5f7fa` |
| Monochrome                             | `#000000` |

The tile stays brand teal in both themes. In the app these are CSS tokens in
`frontend/app/globals.css` (`--brand`, `--brand-node`, `--brand-ink`, and
`--pro` / `--pro-inverse` / `--pro-on-dark` for «برو» in the wordmark).

## Type

- **Wordmark:** Readex Pro 700, with «برو» / "Pro" in Readex Pro 500 in the
  accent. Used only for the product name.
- **Text:** Tajawal (Arabic) — Inter and Sora in the English interface.

The lockup SVGs keep the wordmark as **live text** in Readex Pro (it is not
converted to outlines: no reliable outlining tool with Arabic shaping was
available). Install Readex Pro, or open them in a browser, which loads it
from Google Fonts. The `png/lockup-*@2x.png` exports are rendered with the
real font.

## Regenerating

From `frontend/`:

```sh
node scripts/brand-icons.mjs            # masters here + app icons + PNG exports
node scripts/brand-icons.mjs --lockups  # also the lockup PNGs (Playwright Chromium)
node scripts/brand-icons.mjs --og       # also public/marketing/og.png (the social card)
```

`--lockups` and `--og` need Playwright's Chromium and a network connection
(Readex Pro comes from Google Fonts).

The script writes these masters from `lib/brandMark.js`, then rasterises the
app's icons from them with sharp: `frontend/public/icons/` (`icon-192/512`,
`icon-maskable-192/512`, `apple-touch-icon`, `icon.svg`, `icon-maskable.svg`,
`favicon.svg`, `mark-mono.svg`, `badge-96.png`) and `frontend/public/favicon.ico`
(16 + 32). Commit the results.
