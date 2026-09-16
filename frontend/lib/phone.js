// A phone number as people type it ("0912 345 678", "+249 91 234 5678",
// "00966…") turned into what tel: and wa.me need. WhatsApp only accepts the
// international form without "+", so a local number is completed with the
// dialling code of the country it belongs to; the platform's home market
// (Sudan) is the default when nothing else is known.

export const DEFAULT_PHONE_COUNTRY = "SD";

// ISO-3166 alpha-2 → dialling code, for the markets the platform sells in.
export const DIALLING_CODES = {
  SD: "249", SS: "211", EG: "20", SA: "966", AE: "971", QA: "974", KW: "965",
  BH: "973", OM: "968", JO: "962", IQ: "964", YE: "967", SY: "963", LB: "961",
  PS: "970", LY: "218", TN: "216", DZ: "213", MA: "212", MR: "222", SO: "252",
  DJ: "253", ET: "251", ER: "291", TD: "235", KE: "254", UG: "256", TR: "90",
  GB: "44", US: "1", CA: "1", DE: "49", FR: "33", IN: "91", PK: "92", MY: "60",
};

export function phoneDigits(phone) {
  return String(phone || "").replace(/\D/g, "");
}

// The number in international form (digits only, no "+"), or "" when it
// cannot be a real number. Numbers with a "+" or "00" prefix are trusted as
// written; a number starting with a single 0 is local and gets the country's
// code; anything else is assumed to already carry its code.
export function whatsappNumber(phone, country = DEFAULT_PHONE_COUNTRY) {
  const raw = String(phone || "").trim();
  if (!raw) return "";
  let digits = phoneDigits(raw);
  if (raw.startsWith("+")) {
    // keep as is
  } else if (digits.startsWith("00")) {
    digits = digits.slice(2);
  } else if (digits.startsWith("0")) {
    const code = DIALLING_CODES[String(country || "").toUpperCase()] || DIALLING_CODES[DEFAULT_PHONE_COUNTRY];
    digits = code + digits.replace(/^0+/, "");
  }
  return digits.length >= 8 && digits.length <= 15 ? digits : "";
}

export function whatsappUrl(phone, country) {
  const number = whatsappNumber(phone, country);
  return number ? `https://wa.me/${number}` : "";
}

export function telUrl(phone) {
  const raw = String(phone || "").trim();
  if (!raw) return "";
  const digits = phoneDigits(raw);
  return digits ? `tel:${raw.startsWith("+") ? "+" : ""}${digits}` : "";
}
