// Which tab owns a sale's idempotency key.
//
// The till autosaves its open cart (with the sale's client_uuid) and
// restores it when the page opens; parked carts carry theirs too. A second
// tab of the till restored the same draft — the same key — and when it sold
// a different cart the server answered with the first tab's invoice: the
// second sale was never recorded. Each tab now holds a browser-wide Web
// Lock named after the key of the sale it has open. A tab that restores a
// draft or a parked cart whose key another open tab holds mints a new key
// (and a new printed reference) for its copy.
//
// Without Web Locks (very old browsers) nothing is held and a restored key
// is kept, as before; the server still refuses a different sale under a
// used key (409 client_uuid_conflict).
const PREFIX = "vezano-sale:";
const held = new Map(); // uuid -> release()
const claiming = new Map(); // uuid -> Promise<boolean>

function locks() {
  return typeof navigator !== "undefined" && navigator.locks?.request ? navigator.locks : null;
}

// Resolves true when this tab now holds `uuid` (or cannot tell), false when
// another tab holds it.
export function claimSaleKey(uuid) {
  if (!uuid || held.has(uuid)) return Promise.resolve(true);
  const api = locks();
  if (!api) return Promise.resolve(true);
  if (claiming.has(uuid)) return claiming.get(uuid);
  const attempt = new Promise((resolve) => {
    api.request(PREFIX + uuid, { ifAvailable: true }, (lock) => {
      if (!lock) { resolve(false); return null; }
      // Held until released: the callback's promise is the lock's lifetime.
      return new Promise((release) => { held.set(uuid, release); resolve(true); });
    }).catch(() => resolve(true));
  }).finally(() => claiming.delete(uuid));
  claiming.set(uuid, attempt);
  return attempt;
}

export function releaseSaleKey(uuid) {
  const release = held.get(uuid);
  held.delete(uuid);
  release?.();
}

export function holdsSaleKey(uuid) {
  return held.has(uuid);
}
