// EAN-13 barcode rendering as inline SVG.
//
// Written by hand rather than pulling in a barcode library: the encoding is a
// small fixed table, and this keeps the dependency surface unchanged. Output is
// plain SVG so it prints crisply at any size and needs no canvas or fonts.
//
// Symbol layout (95 modules): start guard | 6 left digits | centre guard |
// 6 right digits | end guard. The first digit is not drawn as bars — it is
// encoded in the L/G parity pattern of the six left-hand digits.

const L = [
  "0001101", "0011001", "0010011", "0111101", "0100011",
  "0110001", "0101111", "0111011", "0110111", "0001011",
];
const G = [
  "0100111", "0110011", "0011011", "0100001", "0011101",
  "0111001", "0000101", "0010001", "0001001", "0010111",
];
const R = [
  "1110010", "1100110", "1101100", "1000010", "1011100",
  "1001110", "1010000", "1000100", "1001000", "1110100",
];
const PARITY = [
  "LLLLLL", "LLGLGG", "LLGGLG", "LLGGGL", "LGLLGG",
  "LGGLLG", "LGGGLL", "LGLGLG", "LGLGGL", "LGGLGL",
];

export function ean13CheckDigit(twelve) {
  const digits = String(twelve).slice(0, 12).split("").map(Number);
  const sum = digits.reduce((acc, d, i) => acc + d * (i % 2 ? 3 : 1), 0);
  return String((10 - (sum % 10)) % 10);
}

export function isValidEan13(code) {
  const s = String(code || "").trim();
  if (!/^\d{13}$/.test(s)) return false;
  return ean13CheckDigit(s.slice(0, 12)) === s[12];
}

/** Full 95-module bit pattern for a 13-digit code. */
function modules(code) {
  const d = code.split("").map(Number);
  const parity = PARITY[d[0]];
  let bits = "101"; // start guard
  for (let i = 0; i < 6; i++) {
    const digit = d[i + 1];
    bits += parity[i] === "L" ? L[digit] : G[digit];
  }
  bits += "01010"; // centre guard
  for (let i = 0; i < 6; i++) bits += R[d[i + 7]];
  bits += "101"; // end guard
  return bits;
}

/**
 * Render an EAN-13 as an SVG string. Guard bars extend below the symbol so the
 * human-readable digits sit in the standard positions.
 */
export function ean13Svg(code, { moduleWidth = 2, height = 60, showText = true } = {}) {
  const s = String(code || "").trim();
  if (!isValidEan13(s)) return "";

  const bits = modules(s);
  const quiet = 11 * moduleWidth; // required quiet zone
  const width = quiet * 2 + bits.length * moduleWidth;
  const textH = showText ? 14 : 0;
  const total = height + textH;
  // Guard positions that run full-length (start, centre, end).
  const isGuard = (i) =>
    i < 3 || (i >= 45 && i < 50) || i >= bits.length - 3;

  let bars = "";
  for (let i = 0; i < bits.length; i++) {
    if (bits[i] !== "1") continue;
    const h = isGuard(i) ? height + (showText ? 6 : 0) : height;
    bars += `<rect x="${quiet + i * moduleWidth}" y="0" width="${moduleWidth}" height="${h}" fill="currentColor"/>`;
  }

  let text = "";
  if (showText) {
    const y = total;
    const mono = "font-family='ui-monospace,monospace' font-size='12'";
    // Standard grouping: 1 digit outside, then 6 + 6 under each half.
    text =
      `<text x="0" y="${y}" ${mono} fill="currentColor">${s[0]}</text>` +
      `<text x="${quiet + 3 * moduleWidth}" y="${y}" ${mono} fill="currentColor">${s.slice(1, 7)}</text>` +
      `<text x="${quiet + 50 * moduleWidth}" y="${y}" ${mono} fill="currentColor">${s.slice(7)}</text>`;
  }

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${total}" viewBox="0 0 ${width} ${total}" role="img" aria-label="Barcode ${s}">${bars}${text}</svg>`;
}
