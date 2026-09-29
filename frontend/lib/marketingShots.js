// The product screenshots on the public pages (components/marketing/Shot.jsx):
// real captures of a local seed_demo company, made and encoded by
// scripts/marketing-shots.mjs. Each one exists per language and theme as
// WebP at several widths (for srcset) plus one light JPEG per language for
// browsers without WebP. The layout box is the capture's CSS size
// (SHOT_SIZE); the widest file is SHOT_WIDTHS' last.
//
// Files: /marketing/shots/<name>.<language>.<theme>.<width>.webp and
//        /marketing/shots/<name>.<language>.light.jpg

export const SHOT_SIZE = { width: 1440, height: 900 };
export const SHOT_WIDTHS = [720, 1440];

// `languages`: the captures that exist (a page in another language falls
// back to the first); `themes`: dark only where a dark capture exists.
export const SHOTS = {
  dashboard: { languages: ["ar"], themes: ["light", "dark"] },
  pos: { languages: ["ar"], themes: ["light", "dark"] },
  inventory: { languages: ["ar"], themes: ["light"] },
  debts: { languages: ["ar"], themes: ["light"] },
  users: { languages: ["ar"], themes: ["light"] },
  "store-page": { languages: ["ar"], themes: ["light", "dark"] },
};

const DIR = "/marketing/shots";

export function shotLanguage(name, language) {
  const spec = SHOTS[name];
  if (!spec) return null;
  return spec.languages.includes(language) ? language : spec.languages[0];
}

export function shotFile(name, language, theme, width) {
  return `${DIR}/${name}.${language}.${theme}.${width}.webp`;
}

export function shotFallback(name, language) {
  return `${DIR}/${name}.${language}.light.jpg`;
}

export function shotSrcSet(name, language, theme) {
  return SHOT_WIDTHS.map((width) => `${shotFile(name, language, theme, width)} ${width}w`).join(", ");
}

// Every file the manifest promises, for the test that they all exist.
export function allShotFiles() {
  const files = [];
  for (const [name, spec] of Object.entries(SHOTS)) {
    for (const language of spec.languages) {
      files.push(shotFallback(name, language));
      for (const theme of spec.themes) for (const width of SHOT_WIDTHS) files.push(shotFile(name, language, theme, width));
    }
  }
  return files;
}
