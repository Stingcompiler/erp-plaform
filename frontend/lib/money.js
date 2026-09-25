// Money on screen and on paper, one rule everywhere:
//
//   - always two decimals, grouped thousands, Latin digits (the digits on
//     the till, the receipt and the bank app are the same ones);
//   - the currency as a short label after the figure — "ج.س" in the Arabic
//     UI and "SDG" in English for the Sudanese pound (the stored code may be
//     SDG, SD or SDD), the ISO code for anything else in English, and the
//     usual Arabic abbreviation where one exists;
//   - no figure (a report that did not load) shows a dash, never 0.00.
//
// Nothing here changes stored data or the API: amounts stay decimal strings
// on the wire, this only decides how they read.

// Two-decimal rounding that agrees with the server.
//
// The API rounds half-up on exact decimals (Decimal ROUND_HALF_UP). Rounding
// binary floats directly does not: 10.075 is stored as 10.07499999…, so
// Math.round(10.075 * 100) gives 1007 and the till asked for 0.01 less than
// the invoice — which the server then read as an unpaid balance, i.e. a
// credit sale, and refused without a named customer. Trimming the float
// noise with toPrecision(12) first recovers the decimal the cashier sees.
export function round2(value) {
  const n = Number(value) || 0;
  const cents = Math.round(Number((Math.abs(n) * 100).toPrecision(12)));
  return (Math.sign(n) * cents) / 100;
}

const AMOUNT = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const SUDANESE_POUND = new Set(["SDG", "SD", "SDD", "ج.س"]);

// Arabic abbreviations for the currencies a Sudanese business meets.
const AR_LABEL = {
  SDG: "ج.س",
  USD: "دولار",
  EUR: "يورو",
  SAR: "ر.س",
  AED: "د.إ",
  EGP: "ج.م",
  QAR: "ر.ق",
  KWD: "د.ك",
  BHD: "د.ب",
  OMR: "ر.ع",
};

function isBlank(value) {
  return value === null || value === undefined || value === "";
}

// "1,234.50" — the figure alone. `empty` (e.g. "—") is shown for a missing
// value instead of 0.00; without it a missing value reads as zero, as the
// old per-screen helpers did.
export function formatAmount(value, { empty } = {}) {
  if (isBlank(value) && empty !== undefined) return empty;
  const n = Number(value);
  if (!Number.isFinite(n)) return empty !== undefined ? empty : AMOUNT.format(0);
  // round2 first: 10.075 must read 10.08, as the server rounds it.
  const text = AMOUNT.format(round2(n));
  return text === "-0.00" ? "0.00" : text;
}

// The currency's label in the UI language. Unknown codes read as themselves.
export function currencyLabel(code, language = "ar") {
  const raw = String(code || "").trim();
  if (!raw) return "";
  const upper = raw.toUpperCase();
  const iso = SUDANESE_POUND.has(upper) || SUDANESE_POUND.has(raw) ? "SDG" : upper;
  if (language === "ar") return AR_LABEL[iso] || iso;
  return iso;
}

// "1,234.50 ج.س" / "1,234.50 SDG". Without a currency, the figure alone.
export function formatMoney(value, { currency, language = "ar", empty } = {}) {
  const amount = formatAmount(value, { empty });
  if (empty !== undefined && amount === empty) return amount;
  const label = currencyLabel(currency, language);
  return label ? `${amount} ${label}` : amount;
}
