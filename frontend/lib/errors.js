// One readable sentence for any failed request.
//
// Screens used to print whatever the API returned — `Object.values(data).flat()`
// — which put raw English validation text (or a whole payload) in front of an
// Arabic-speaking shopkeeper. A message is only useful if the reader knows what
// to do next, so this maps what the backend actually distinguishes (an error
// `code`, then the HTTP status, then "no response at all") onto sentences that
// exist in both languages, and falls back to the caller's own sentence.
//
// The API's technical text is not thrown away: `errorDetail` returns it for a
// muted second line or a `title` attribute where there is room for it.

// 400 is deliberately absent: a bad request is about the form the user just
// filled, so the caller's own sentence says more than a generic one.
const STATUS_KEY = {
  401: "errors.session",
  403: "errors.forbidden",
  404: "errors.notFound",
  409: "errors.conflict",
  413: "errors.tooLarge",
  415: "errors.badFile",
  429: "errors.tooMany",
  503: "errors.unavailable",
};

function payloadOf(error) {
  const data = error?.response?.data;
  return data && typeof data === "object" && !Array.isArray(data) ? data : null;
}

/** The API's own words, for a secondary line — never the whole payload. */
export function errorDetail(error) {
  const data = payloadOf(error);
  if (!data) return "";
  if (typeof data.detail === "string") return data.detail;
  const first = Object.values(data).flat().find((v) => typeof v === "string");
  return first || "";
}

/**
 * `errorText(err, t, "finance.saveError")` — a sentence to show the user.
 * Pass the key of a sentence that describes *this* action; it is used when the
 * failure carries nothing more specific.
 */
export function errorText(error, t, fallbackKey = "errors.generic") {
  const fallback = () => (fallbackKey ? t(fallbackKey) : t("errors.generic"));
  const known = (key) => (key && t(key) !== key ? t(key) : null);

  // No response: the request never reached the server (offline, dropped
  // connection, timeout). Saying "check your connection" is the only honest
  // advice here, and it is the common case on a shop's mobile data.
  if (error?.response == null) {
    const offline = typeof navigator !== "undefined" && navigator.onLine === false;
    return t(offline ? "errors.offline" : "errors.network");
  }

  const status = error.response.status;
  const data = payloadOf(error);
  // A `code` is the backend saying exactly what went wrong; translate it when
  // we have words for it (errors.codes.<code>).
  const coded = typeof data?.code === "string" ? known(`errors.codes.${data.code}`) : null;
  if (coded) return coded;

  // The status is the one technical fact worth showing on a 5xx: it is what
  // support will ask for, and it is not a payload dump.
  if (status >= 500) return `${t("errors.server")} (HTTP ${status})`;

  // The server translates its refusals into the reader's language (the
  // language cookie drives Django's LocaleMiddleware), and a specific
  // sentence — "the amount exceeds the balance due (250.00)" — beats any
  // generic one. It is shown only when it really is in the reader's
  // language: an untranslated English message on an Arabic screen is the
  // raw text this helper exists to keep away.
  const own = serverSentence(data, t);
  if (own) return own;
  return known(STATUS_KEY[status]) || fallback();
}

const ARABIC = /[\u0600-\u06FF]/;
const LATIN = /[A-Za-z]/;

function serverSentence(data, t) {
  if (!data) return "";
  const message = typeof data.detail === "string"
    ? data.detail
    : Object.values(data).flat().find((v) => typeof v === "string") || "";
  if (!message || message.length > 300) return "";
  const arabicScreen = ARABIC.test(t("errors.generic"));
  return arabicScreen ? (ARABIC.test(message) ? message : "") : (LATIN.test(message) ? message : "");
}

