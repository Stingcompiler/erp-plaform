// FAQPage blocks (schema.org) for the pages that show questions. Split from
// lib/seo.js because the home page renders its block on the client, and
// lib/seo.js reaches every content article through lib/marketingMeta.js —
// ~30 KB of gzip the home page does not need. lib/seo.js re-exports these.
import { homeAr, homeEn, pricingAr, pricingEn } from "./marketingI18n.js";

export function faqPage(pairs) {
  return {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: pairs.map(([question, answer]) => ({
      "@type": "Question",
      name: question,
      acceptedAnswer: { "@type": "Answer", text: answer },
    })),
  };
}

// The same questions the page shows in that language; a FAQPage block whose
// content is not visible on the page is against Google's guidelines.
export const homeFaqJsonLd = (language = "ar") => faqPage((language === "en" ? homeEn : homeAr).faq);
export const pricingFaqJsonLd = (language = "ar") =>
  faqPage((language === "en" ? pricingEn : pricingAr).faq);
