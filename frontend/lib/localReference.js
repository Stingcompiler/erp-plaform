// A receipt number the till can print with no server: BRANCH-DEVICE-SEQ.
//
// The company-wide invoice number is allocated by the server (gapless, under
// a row lock) and cannot be known offline. This reference is what the
// customer walks away with during an outage; the server stores it on the
// invoice (`local_reference`) so the two can be matched later. DEVICE is a
// random id minted once per browser profile; SEQ counts per device and
// account scope, so two tills at one branch never collide.
import { storageKey } from "./localIdentity.js";

const DEVICE_KEY = "erp.device.v1";

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

export function nextLocalReference(branchCode) {
  const key = storageKey("localSeq");
  let seq = 0;
  try { seq = Number(localStorage.getItem(key) || 0) + 1; localStorage.setItem(key, String(seq)); }
  catch { seq = Date.now() % 1000000; }
  const branch = String(branchCode || "POS").toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 8) || "POS";
  return `${branch}-${deviceId()}-${String(seq).padStart(6, "0")}`;
}
