import { storageKey } from "./localIdentity.js";

// One key per operation avoids one tab overwriting another tab's entire queue.
// A failed write MUST throw: the caller keeps the sale on screen until durable.
function prefix(scope) { return `${storageKey("sync", scope)}:`; }
function list(scope) {
  const keyPrefix = prefix(scope);
  const rows = [];
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (key?.startsWith(keyPrefix)) {
      const row = JSON.parse(localStorage.getItem(key));
      if (!row?.client_uuid || !row.payload) throw new Error("Invalid saved operation.");
      rows.push(row);
    }
  }
  return rows.sort((a, b) => a.queued_at - b.queued_at);
}
export const queue = {
  list,
  count: (scope) => list(scope).length,
  hasLegacy: () => Boolean(localStorage.getItem("erp.sync.queue.v1") &&
    localStorage.getItem("erp.sync.queue.v1") !== "[]"),
  enqueue(opType, payload, scope) {
    const id = payload.client_uuid || crypto.randomUUID();
    const key = prefix(scope) + id;
    // Keep the original body if an uncertain network request is retried.
    const previous = localStorage.getItem(key);
    if (previous) return JSON.parse(previous);
    const op = { op_type: opType, client_uuid: id,
      payload: { ...payload, client_uuid: id }, queued_at: Date.now(), error: null };
    localStorage.setItem(key, JSON.stringify(op));
    return op;
  },
  confirmation(id, scope) {
    try { return JSON.parse(localStorage.getItem(`${storageKey("syncReceipt", scope)}:${id}`) || "null"); }
    catch { return null; }
  },
  acknowledge(sent, results, scope) {
    if (!Array.isArray(results)) throw new Error("Missing synchronization results.");
    const accepted = new Map(results.map((r) => [r.client_uuid, r]));
    for (const op of sent) {
      const result = accepted.get(op.client_uuid);
      const key = prefix(scope) + op.client_uuid;
      if (result?.status === "applied" || result?.status === "duplicate") {
        if (op.op_type === "pos_checkout" && result.id) {
          localStorage.setItem(`${storageKey("syncReceipt", scope)}:${op.client_uuid}`,
            JSON.stringify({ id: result.id, confirmed_at: Date.now() }));
        }
        localStorage.removeItem(key);
      } else {
        const current = localStorage.getItem(key);
        if (current) localStorage.setItem(key, JSON.stringify({ ...JSON.parse(current),
          error: result?.error || "No confirmation received for this operation." }));
      }
    }
  },
};
