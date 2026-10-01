// Pure helpers of the password reset page (app/forgot-password): the
// strength hints under the new password and the deep link an
// administrator's reset email opens (`?email=&challenge=`). node tests
// them (tests/passwordReset.test.mjs).

export const MIN_LENGTH = 10;

// What the hints list shows as met. `length` and `notNumeric` mirror two
// of the server's validators (MinimumLength 10, Numeric); `mix` is advice;
// `match` compares the two fields. The server still has the final word
// (it also refuses common passwords and ones like the account's name).
export function passwordChecks(password, confirm) {
  const value = String(password || "");
  return {
    length: value.length >= MIN_LENGTH,
    notNumeric: value.length > 0 && !/^\d+$/.test(value),
    mix: /\p{L}/u.test(value) && /[^\p{L}]/u.test(value),
    match: value.length > 0 && value === String(confirm || ""),
  };
}

// Whether the form may be sent: the required checks, not the advice.
export function passwordReady(checks) {
  return Boolean(checks.length && checks.notNumeric && checks.match);
}

// `?email=a@b.c&challenge=…` from an administrator's reset email: the page
// opens on the code step for that challenge. Anything malformed is ignored.
export function resetDeepLink(search) {
  const params = new URLSearchParams(String(search || ""));
  const email = (params.get("email") || "").trim().slice(0, 254);
  const challenge = (params.get("challenge") || "").trim();
  if (!email.includes("@") || !/^[A-Za-z0-9_-]{16,64}$/.test(challenge)) return null;
  return { email, challenge };
}
