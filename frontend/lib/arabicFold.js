// Arabic-insensitive matching for the offline search, the same fold the
// server applies (backend/core/arabic.py fold_arabic): hamza-carrying alefs
// to a bare alef, taa marbuta to haa, alef maqsura and yaa-hamza to yaa,
// waw-hamza to waw; tatweel, tanween/harakat/shadda/sukun (U+064B–U+0652)
// and the superscript alef dropped; Arabic-Indic and Persian digits to
// ASCII. A till offline must find "أرز" when the cashier types "ارز",
// exactly as it does online. Keep the two tables in step.

const FOLDS = new Map([
  ["أ", "ا"], ["إ", "ا"], ["آ", "ا"], ["ٱ", "ا"], // أ إ آ ٱ → ا
  ["ة", "ه"], // ة → ه
  ["ى", "ي"], // ى → ي
  ["ؤ", "و"], // ؤ → و
  ["ئ", "ي"], // ئ → ي
  ["ـ", ""], // tatweel
  ["ٰ", ""], // superscript alef
]);
for (let code = 0x064b; code <= 0x0652; code += 1) FOLDS.set(String.fromCharCode(code), "");
for (let digit = 0; digit < 10; digit += 1) {
  FOLDS.set(String.fromCharCode(0x0660 + digit), String(digit)); // ٠-٩
  FOLDS.set(String.fromCharCode(0x06f0 + digit), String(digit)); // ۰-۹ (Persian)
}

export function foldArabic(text) {
  let out = "";
  for (const ch of String(text ?? "")) {
    const folded = FOLDS.get(ch);
    out += folded === undefined ? ch : folded;
  }
  return out;
}

// The search form used on both sides of a comparison: folded and lowercased
// (the server's icontains ignores Latin case too).
export function searchForm(text) {
  return foldArabic(text).toLowerCase();
}

// Like the server's search filter: the query splits on whitespace and every
// term must appear in one of the fields (name, SKU, barcode…).
export function matchesSearch(query, fields) {
  const terms = searchForm(query).split(/\s+/).filter(Boolean);
  if (!terms.length) return false;
  const haystack = fields.map((field) => searchForm(field ?? "")).filter(Boolean);
  return terms.every((term) => haystack.some((field) => field.includes(term)));
}
