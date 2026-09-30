// The catalog of the public marketing pages (app/(marketing)): only the
// namespaces they use, built from lib/marketingI18n.js alone, so a visitor
// never downloads the app's dictionary (~430 KB, most of it screens they
// cannot open). tests/publicI18n.test.mjs checks that every key the public
// pages name is here, and that each text is the one the app catalog has.
import { translateFrom } from "./i18nCore.js";
import {
  contentAr, contentEn, homeAr, homeEn, installAr, installEn, landingAr, landingEn, pricingAr, pricingEn,
  productAr, productEn, registerAr, registerEn, registrationAr, registrationEn, sharedAr, sharedEn, trackAr, trackEn,
} from "./marketingI18n.js";

export const PUBLIC_CATALOG = {
  en: {
    ...sharedEn,
    landing: landingEn, content: contentEn, registration: registrationEn, install: installEn,
    home: homeEn, pricing: pricingEn, product: productEn, register: registerEn, track: trackEn,
  },
  ar: {
    ...sharedAr,
    landing: landingAr, content: contentAr, registration: registrationAr, install: installAr,
    home: homeAr, pricing: pricingAr, product: productAr, register: registerAr, track: trackAr,
  },
};

export function translatePublic(lang, key, vars) {
  return translateFrom(PUBLIC_CATALOG, lang, key, vars);
}
