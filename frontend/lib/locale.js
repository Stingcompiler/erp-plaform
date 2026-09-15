// Language as a property of the URL, for the public pages only.
//
// The marketing pages exist twice: Arabic at the root (/, /product/, ...) and
// English under /en/ (/en/, /en/product/, ...). A crawler cannot click the
// language toggle, so each language needs its own address; hreflang tags on
// both versions tell search engines they are translations of one page.
//
// The signed-in app is unaffected: it has one URL per screen and follows the
// stored preference, as before. Pure functions, no React, so they are unit
// tested directly.

export const EN_PREFIX = "/en";

// Root-relative public pages, without the language prefix and without the
// trailing slash the export adds.
export const MARKETING_PATHS = ["/", "/product", "/pricing", "/register"];

function stripTrailingSlash(path) {
  return path.length > 1 && path.endsWith("/") ? path.slice(0, -1) : path;
}

function splitPath(path) {
  const match = /^([^?#]*)(.*)$/.exec(path);
  return [match[1], match[2]];
}

// "en" for /en and anything below it, "ar" for an Arabic marketing page,
// null for everything else (the app, sign-in, unknown routes).
export function marketingLanguage(pathname) {
  if (!pathname) return null;
  const [bare] = splitPath(pathname);
  if (bare === EN_PREFIX || bare.startsWith(`${EN_PREFIX}/`)) return "en";
  return MARKETING_PATHS.includes(stripTrailingSlash(bare)) ? "ar" : null;
}

// The same page in the other language, keeping query string and hash:
// counterpartPath("/en/pricing/", "ar") -> "/pricing/"
// counterpartPath("/register?plan=1", "en") -> "/en/register?plan=1"
export function counterpartPath(pathname, language) {
  const [bare, suffix] = splitPath(pathname);
  let root = bare;
  if (bare === EN_PREFIX) root = "/";
  else if (bare.startsWith(`${EN_PREFIX}/`)) root = bare.slice(EN_PREFIX.length);
  return localizePath(root, language) + suffix;
}

// A marketing href written for the Arabic root, in the given language:
// localizePath("/pricing", "en") -> "/en/pricing"
// localizePath("/#contact", "en") -> "/en/#contact"
// localizePath("/", "en") -> "/en/"
export function localizePath(path, language) {
  if (language !== "en") return path;
  const [bare, suffix] = splitPath(path);
  if (bare === "/" || bare === "") return `${EN_PREFIX}/${suffix}`;
  return `${EN_PREFIX}${bare}${suffix}`;
}
