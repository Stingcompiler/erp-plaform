/**
 * Code 128 as an SVG string, for barcodes that are not EAN-13.
 *
 * Shops type in whatever their supplier printed, or a code of their own
 * ("A-102", a 13-digit number with the wrong check digit). An EAN-13 renderer
 * draws nothing for those, so the label came out with a name and a price and
 * no bars. Every till scanner reads Code 128 out of the box.
 *
 * All-digit codes use set C (two digits a symbol, half as wide, so a 13-digit
 * code still fits a 40 mm label with bars a thermal head can draw), switching
 * to B for an odd last digit; anything else printable uses set B. Characters
 * outside printable ASCII cannot be encoded and return "".
 */

// Bar/space widths (in modules) of symbols 0..106. 103-105 are Start A/B/C,
// 106 is Stop (with its trailing bar).
export const PATTERNS = [
  "212222", "222122", "222221", "121223", "121322", "131222", "122213", "122312", "132212", "221213",
  "221312", "231212", "112232", "122132", "122231", "113222", "123122", "123221", "223211", "221132",
  "221231", "213212", "223112", "312131", "311222", "321122", "321221", "312212", "322112", "322211",
  "212123", "212321", "232121", "111323", "131123", "131321", "112313", "132113", "132311", "211313",
  "231113", "231311", "112133", "112331", "132131", "113123", "113321", "133121", "313121", "211331",
  "231131", "213113", "213311", "213131", "311123", "311321", "331121", "312113", "312311", "332111",
  "314111", "221411", "431111", "111224", "111422", "121124", "121421", "141122", "141221", "112214",
  "112412", "122114", "122411", "142112", "142211", "241211", "221114", "413111", "241112", "134111",
  "111242", "121142", "121241", "114212", "124112", "124211", "411212", "421112", "421211", "212141",
  "214121", "412121", "111143", "111341", "131141", "114113", "114311", "411113", "411311", "113141",
  "114131", "311141", "411131", "211412", "211214", "211232", "2331112",
];

const CODE_B = 100;
const START_B = 104;
const START_C = 105;
const STOP = 106;

/** The symbol values for `code`, start and check symbol included; null if it cannot be encoded. */
export function code128Symbols(code) {
  const s = String(code ?? "");
  if (!s) return null;
  let symbols;
  if (/^\d+$/.test(s) && s.length > 1) {
    symbols = [START_C];
    const even = s.length - (s.length % 2);
    for (let i = 0; i < even; i += 2) symbols.push(Number(s.slice(i, i + 2)));
    // An odd digit left over switches to set B for its last character.
    if (even < s.length) symbols.push(CODE_B, s.charCodeAt(even) - 32);
  } else {
    symbols = [START_B];
    for (const ch of s) {
      const c = ch.codePointAt(0);
      if (c < 32 || c > 126) return null;
      symbols.push(c - 32);
    }
  }
  let sum = symbols[0];
  for (let i = 1; i < symbols.length; i++) sum += symbols[i] * i;
  symbols.push(sum % 103);
  symbols.push(STOP);
  return symbols;
}

export function code128Svg(code, { moduleWidth = 2, height = 60 } = {}) {
  const symbols = code128Symbols(code);
  if (!symbols) return "";
  const quiet = 10 * moduleWidth;
  let x = quiet;
  let bars = "";
  for (const value of symbols) {
    const widths = PATTERNS[value];
    for (let i = 0; i < widths.length; i++) {
      const w = Number(widths[i]) * moduleWidth;
      if (i % 2 === 0) bars += `<rect x="${x}" y="0" width="${w}" height="${height}" fill="currentColor"/>`;
      x += w;
    }
  }
  const width = x + quiet;
  const label = String(code).replace(/[<>&"]/g, "");
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-label="Barcode ${label}">${bars}</svg>`;
}
