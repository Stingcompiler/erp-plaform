// The last successful identity + permission map, kept so the app can open
// while the server is unreachable. Without it, any network failure on
// /auth/me looked like "not signed in" and bounced the cashier to a login
// screen that itself needs the server — the offline queue was there but
// unreachable. Holds no tokens: the auth cookie is still what authorises
// requests once connectivity returns. Cleared on logout and on a real 401.
const KEY = "erp.session.v1";

export function readSessionCache() {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed?.me?.id ? parsed : null;
  } catch {
    return null;
  }
}

export function writeSessionCache(me, access) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(
      KEY,
      JSON.stringify({ me, access: access || {}, cached_at: new Date().toISOString() }),
    );
  } catch {
    /* quota / private mode: the cache is a convenience, never required */
  }
}

export function clearSessionCache() {
  if (typeof window === "undefined") return;
  try { window.localStorage.removeItem(KEY); } catch { /* ignore */ }
}

// A failure that says nothing about whether the user is signed in: no
// response at all (offline, DNS, timeout) or the server itself falling over.
export function isConnectivityFailure(error) {
  const status = error?.response?.status;
  return !status || status >= 500;
}
