// Tiny observable: "the screen is showing data recalled from the local
// cache, fetched at <ts>". api.js sets it when a GET is answered from the
// cache; StaleDataBanner shows it; a fresh cacheable GET clears it.

let staleAt = null;
const listeners = new Set();

function emit() { listeners.forEach((fn) => fn(staleAt)); }

export function markStale(ts) {
  // Keep the OLDEST timestamp on screen: that is the figure the person
  // should distrust most.
  if (staleAt === null || ts < staleAt) { staleAt = ts; emit(); }
}
export function clearStale() { if (staleAt !== null) { staleAt = null; emit(); } }
export function getStale() { return staleAt; }
export function subscribeStale(fn) { listeners.add(fn); return () => listeners.delete(fn); }
