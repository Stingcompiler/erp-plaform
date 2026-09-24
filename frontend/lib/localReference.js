// A receipt number the till can print with no server: BRANCH-DEVICE-SEQ.
//
// The company-wide invoice number is allocated by the server (gapless, under
// a row lock) and cannot be known offline. This reference is what the
// customer walks away with during an outage; the server stores it on the
// invoice (`local_reference`) so the two can be matched later. DEVICE is a
// random id minted once per browser profile; SEQ counts per DEVICE, shared
// by every account that signs in on it. (It used to count per account: two
// cashiers sharing one tablet printed the same MAIN-AB12-000001 and the
// second sale was refused by the server.)

const DEVICE_KEY = "erp.device.v1";
const SEQ_KEY = "erp.localSeq.device.v1";
// The old per-account counters (storageKey("localSeq") in localIdentity.js).
const LEGACY_SEQ_PREFIX = "erp.localSeq.v2:";

export function deviceId() {
  try {
    let id = localStorage.getItem(DEVICE_KEY);
    if (!id) {
      id = crypto.randomUUID().replace(/-/g, "").slice(0, 4).toUpperCase();
      localStorage.setItem(DEVICE_KEY, id);
    }
    return id;
  } catch {
    return "WEB";
  }
}

// The highest number this device has printed, under any account. Taking
// the maximum over the old per-account counters as well means a number
// never goes backwards after the upgrade (or if an old tab still writes one).
function highestPrinted() {
  let max = Number(localStorage.getItem(SEQ_KEY) || 0) || 0;
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (key?.startsWith(LEGACY_SEQ_PREFIX)) max = Math.max(max, Number(localStorage.getItem(key) || 0) || 0);
  }
  return max;
}

export function nextLocalReference(branchCode) {
  let seq = 0;
  try { seq = highestPrinted() + 1; localStorage.setItem(SEQ_KEY, String(seq)); }
  catch { seq = Date.now() % 1000000; }
  const branch = String(branchCode || "POS").toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 8) || "POS";
  return `${branch}-${deviceId()}-${String(seq).padStart(6, "0")}`;
}
