"use client";

import { useI18n } from "@/app/providers/I18nProvider";

// The product name as a wordmark: «فيزانو برو» in Arabic, "Vezano Pro" in
// English, set in Readex Pro (loaded in app/layout.js as --font-readex and
// used for nothing else) with «برو» / "Pro" in the brand accent.
//
// `tone` picks the accent that reads on the surface behind the wordmark:
//   "default" — the page's own paper/surface (follows light/dark),
//   "inverse" — a bg-ink panel, which flips light/dark against the page,
//   "dark"    — the sidebar, which is dark in both themes.
const PRO_TONE = {
  default: "text-pro",
  inverse: "text-pro-inverse",
  dark: "text-pro-on-dark",
};

const NAME = {
  ar: ["فيزانو", "برو"],
  en: ["Vezano", "Pro"],
};

export default function Wordmark({ language: forced, tone = "default", className = "" }) {
  const { language } = useI18n();
  const code = (forced || language) === "en" ? "en" : "ar";
  const [base, pro] = NAME[code];
  return (
    <span
      dir={code === "ar" ? "rtl" : "ltr"}
      lang={code}
      className={`font-wordmark whitespace-nowrap font-bold tracking-normal ${className}`}
    >
      {base} <span className={`font-medium ${PRO_TONE[tone] || PRO_TONE.default}`}>{pro}</span>
    </span>
  );
}
