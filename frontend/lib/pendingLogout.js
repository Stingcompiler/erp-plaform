// A sign-out the server has not heard about yet.
//
// The session lives in HttpOnly cookies the page cannot delete: only the
// server's /auth/logout/ answer clears them (and blacklists the refresh
// token). Signing out with no connection used to clear the screen and
// nothing else, so the next person to open the app on that shared tablet
// once the connection returned was signed straight back in as the cashier
// who had left. Now the sign-out is remembered here and sent before
// anything else when the server is reachable again; until it has gone
// through, the app treats the device as signed out and never refreshes the
// old session.
const KEY = "vezano.pendingLogout.v1";

function storage() {
  try { return typeof window !== "undefined" ? window.localStorage : globalThis.localStorage || null; }
  catch { return null; }
}

export function markPendingLogout(userId = null) {
  try { storage()?.setItem(KEY, JSON.stringify({ at: Date.now(), user: userId ?? null })); }
  catch { /* no storage: the server copy of the sign-out is best effort */ }
}

export function pendingLogout() {
  try {
    const raw = storage()?.getItem(KEY);
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}

export function clearPendingLogout() {
  try { storage()?.removeItem(KEY); } catch { /* ignore */ }
}

// Sends the remembered sign-out once. `send` posts /auth/logout/. Resolves
// true when nothing is (any longer) pending, false while the server is still
// out of reach (no answer, or a 5xx: the server did not get to clear the
// cookies). A 4xx counts as done: the logout endpoint needs no session, so
// there is nothing a retry could change.
let flushing = null;
export function flushPendingLogout(send) {
  if (!pendingLogout()) return Promise.resolve(true);
  flushing ||= (async () => {
    try {
      await send();
      clearPendingLogout();
      return true;
    } catch (error) {
      const status = error?.response?.status;
      if (status && status < 500) { clearPendingLogout(); return true; }
      return false;
    } finally { flushing = null; }
  })();
  return flushing;
}
