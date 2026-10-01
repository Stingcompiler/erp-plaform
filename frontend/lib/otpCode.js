// The email-code steps of the trial form and of vezano.app/track/ (backend:
// website/otp.py, trial_requests.py, request_tracking.py). Pure helpers, so
// node tests them (tests/otpCode.test.mjs); the UI is
// components/marketing/CodeStep.jsx.

export const CODE_LENGTH = 6;

const ARABIC_DIGITS = { "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4", "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
  "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4", "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9" };

// What a visitor typed or pasted ("123 456", "١٢٣٤٥٦", "Code: 123456")
// as at most six ASCII digits.
export function normaliseCode(value) {
  return String(value || "")
    .replace(/[٠-٩۰-۹]/g, (digit) => ARABIC_DIGITS[digit])
    .replace(/\D/g, "")
    .slice(0, CODE_LENGTH);
}

export function isCompleteCode(value) {
  return normaliseCode(value).length === CODE_LENGTH;
}

// Whole seconds from `now` until `until` (both ms), never negative.
export function secondsUntil(until, now = Date.now()) {
  return Math.max(0, Math.ceil((Number(until || 0) - now) / 1000));
}

// "0:45", "12:03": a countdown that reads the same in both languages.
export function formatCountdown(seconds) {
  const total = Math.max(0, Math.floor(Number(seconds) || 0));
  const minutes = Math.floor(total / 60);
  return `${minutes}:${String(total % 60).padStart(2, "0")}`;
}

const KNOWN = new Set([
  "code_expired", "wrong_code", "too_many_attempts", "resend_cooldown", "too_many_codes",
  "email_unavailable", "view_expired", "duplicate_request",
]);

// An API error of the code flows as { code, attemptsLeft, retryAfter,
// whatsapp }. `code` is one of KNOWN, "throttled" (the per-address limit),
// "invalid" (a field the server refused), or "network".
export function codeError(error) {
  const response = error?.response;
  if (!response) return { code: "network" };
  const data = response.data && typeof response.data === "object" ? response.data : {};
  const retryAfter = Number(data.retry_after || response.headers?.["retry-after"]) || 0;
  if (KNOWN.has(data.code)) {
    return {
      code: data.code,
      attemptsLeft: typeof data.attempts_left === "number" ? data.attempts_left : null,
      retryAfter,
      whatsapp: data.whatsapp || "",
    };
  }
  if (response.status === 429) return { code: "throttled", retryAfter };
  if (response.status === 400) return { code: "invalid", fields: data };
  return { code: "network" };
}

// Server field errors ({"email": ["…"]}) as {field: message}, so each sits
// next to its own input.
export function fieldErrors(data) {
  const out = {};
  if (!data || typeof data !== "object") return out;
  for (const [field, value] of Object.entries(data)) {
    const message = Array.isArray(value) ? value[0] : value;
    if (typeof message === "string" && message) out[field] = message;
  }
  return out;
}

// A trial (R…) or demo (D…) reference: those open only with an email code,
// so the tracking page sends such a search to the request flow.
export function isRequestReference(query) {
  const compact = String(query || "").replace(/[\s#]/g, "").toUpperCase();
  return /^[RD][A-Z0-9]{6}$/.test(compact);
}

// The tracking page keeps the verified view for its 30 minutes in this
// tab only (sessionStorage): a reload shows it again without a new code.
export const VIEW_KEY = "vezano.trackRequests.v1";

export function viewRecord(token, expiresIn, now = Date.now()) {
  return { token, until: now + Math.max(0, Number(expiresIn) || 0) * 1000 };
}

export function liveView(record, now = Date.now()) {
  if (!record || typeof record !== "object" || !record.token) return null;
  return Number(record.until) > now ? record : null;
}
