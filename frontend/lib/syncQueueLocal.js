import { storageKey } from "./localIdentity.js";
import { retryPatch } from "./syncRetry.js";

// One key per operation avoids one tab overwriting another tab's entire queue.
// A failed write MUST throw: the caller keeps the sale on screen until durable.
function prefix(scope) { return `${storageKey("sync", scope)}:`; }
// Same person, same company, other branch (see adoptSiblingQueues in
// syncQueue.js): move those rows under the current scope so they are sent.
function adoptSiblings(scope) {
  const [company, user] = String(scope).split(":");
  if (!company || !user) return;
  const mine = prefix(scope);
  const family = `${storageKey("sync", `${company}:${user}:`)}`;
  const keys = [];
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (key?.startsWith(family) && !key.startsWith(mine)) keys.push(key);
  }
  for (const key of keys) {
    const id = key.slice(key.lastIndexOf(":") + 1);
    if (!localStorage.getItem(mine + id)) localStorage.setItem(mine + id, localStorage.getItem(key));
    localStorage.removeItem(key);
  }
}
function list(scope) {
  adoptSiblings(scope);
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
      const settled = ["applied", "duplicate", "discarded"].includes(result?.status);
      if (settled) {
        if (op.op_type === "pos_checkout" && result.id) {
          localStorage.setItem(`${storageKey("syncReceipt", scope)}:${op.client_uuid}`,
            JSON.stringify({ id: result.id, confirmed_at: Date.now() }));
        }
        localStorage.removeItem(key);
      } else if (result?.status === "retry") {
        const current = localStorage.getItem(key);
        if (current) {
          const row = JSON.parse(current);
          localStorage.setItem(key, JSON.stringify({ ...row, ...retryPatch(row) }));
        }
      } else {
        const current = localStorage.getItem(key);
        if (current) localStorage.setItem(key, JSON.stringify({ ...JSON.parse(current),
          error: result?.error || "__no_confirmation__",
          error_field: result?.error_field || null }));
      }
    }
  },
  // Repair a refused operation in place (e.g. attach the customer a sale on
  // account needs) and clear its error so the next sync sends it again.
  amend(id, patch, scope) {
    const key = prefix(scope) + id;
    const current = localStorage.getItem(key);
    if (!current) return null;
    const row = JSON.parse(current);
    const next = { ...row, payload: { ...row.payload, ...patch },
      error: null, error_field: null, attempts: 0, retry_at: null };
    localStorage.setItem(key, JSON.stringify(next));
    return next;
  },
};
