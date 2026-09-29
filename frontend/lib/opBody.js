// Whether two queued bodies are the same operation.
//
// A client_uuid names ONE operation: re-enqueueing it after an uncertain
// request keeps the body first stored. But two till tabs restored the same
// draft, and so the same key, for two DIFFERENT sales; the queue answered
// the second with the first and the second sale was never recorded. For a
// sale the queue now tells a retry (same body) from another sale (different
// lines, amounts, customer...) and gives the other sale a key of its own.
// The times are not part of it: a retry is stamped again when it is sent.
const VOLATILE = new Set(["client_uuid", "occurred_at", "sent_at"]);

function canonical(value, top = false) {
  if (Array.isArray(value)) return `[${value.map((v) => canonical(v)).join(",")}]`;
  if (value && typeof value === "object") {
    const keys = Object.keys(value).filter((k) => !(top && VOLATILE.has(k)) && value[k] !== undefined).sort();
    return `{${keys.map((k) => `${JSON.stringify(k)}:${canonical(value[k])}`).join(",")}}`;
  }
  return JSON.stringify(value ?? null);
}

export function sameBody(a, b) {
  return canonical(a || {}, true) === canonical(b || {}, true);
}

// Operations whose key the queue re-mints for a different body. Only a
// sale: the till starts every new sale with a new key, so a different body
// under a stored key can only be another tab's sale. A form elsewhere may
// legitimately re-send its key with edits after an uncertain request, and
// queueing those edits as a second record would duplicate it.
export const REKEY_ON_CONFLICT = new Set(["pos_checkout"]);

// The payload to store for `opType` when `stored` already holds `id`:
// null to keep the stored row (a retry), or the payload under a new key.
export function rekeyed(opType, stored, payload) {
  if (!stored || !REKEY_ON_CONFLICT.has(opType) || sameBody(stored.payload, payload)) return null;
  const id = crypto.randomUUID();
  return { ...payload, client_uuid: id };
}
