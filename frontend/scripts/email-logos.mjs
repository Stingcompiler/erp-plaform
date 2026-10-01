// Email logos: public/email/logo-{ar,en}.png, the header of every
// transactional email (backend/core/templates/emails/bilingual.html).
//
//   node scripts/email-logos.mjs            (from frontend/)
//
// Email clients drop SVG (Gmail strips it), so the header is a PNG at an
// absolute URL. Each one is the light lockup from design/brand/png/ (rendered
// with the real Readex Pro by `brand-icons.mjs --lockups`) on a white rounded
// plate, 240×60 shown, drawn at 2× (480×120). The plate is opaque on purpose:
// clients that darken the email in dark mode (Gmail, Outlook) recolour the
// background but never the image, and a dark-ink wordmark on transparency
// would vanish there. Commit public/email and the rebuilt out/ afterwards.
import { mkdirSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import sharp from "sharp";

const at = (base) => (p) => fileURLToPath(new URL(`${base}${p}`, import.meta.url));
const pub = at("../public/");
const design = at("../../design/brand/");
mkdirSync(pub("email"), { recursive: true });

// Shown at 240×60 (core/mailer.py LOGO_WIDTH/HEIGHT), drawn at 2×.
const SCALE = 2;
const WIDTH = 240 * SCALE;
const HEIGHT = 60 * SCALE;
const RADIUS = 14 * SCALE;
// The lockup is 80 units tall with the 64-unit tile inside: at 44 the tile
// draws at 35px and the wordmark keeps ~24px of plate on either side.
const LOCKUP_HEIGHT = 44 * SCALE;

const plate = Buffer.from(
  `<svg xmlns="http://www.w3.org/2000/svg" width="${WIDTH}" height="${HEIGHT}">` +
    `<rect width="${WIDTH}" height="${HEIGHT}" rx="${RADIUS}" fill="#ffffff"/></svg>`,
);

for (const language of ["ar", "en"]) {
  const lockup = await sharp(design(`png/lockup-${language}-light@2x.png`))
    .resize({ height: LOCKUP_HEIGHT })
    .png()
    .toBuffer();
  const { width } = await sharp(lockup).metadata();
  const image = await sharp(plate)
    .composite([
      {
        input: lockup,
        left: Math.round((WIDTH - width) / 2),
        top: Math.round((HEIGHT - LOCKUP_HEIGHT) / 2),
      },
    ])
    .png({ compressionLevel: 9, palette: false })
    .toBuffer();
  writeFileSync(pub(`email/logo-${language}.png`), image);
}

console.log("email logos written: public/email/logo-ar.png, public/email/logo-en.png");
