"use client";

// A small offline-first queue for write operations that couldn't reach the
// server. Operations are shaped like sync API operations
// ({ op_type, client_uuid, payload }) and persisted to localStorage so they
// survive reloads. Draining batches them to POST /api/sync/push/.
//
// Note: this is a real (self-hosted) Next.js app, so localStorage is the
// appropriate persistence layer for offline-first behaviour.

const KEY = "erp.sync.queue.v1";

function read() {
  if (typeof window === "undefined") return [];
  try {
    return JSON.parse(window.localStorage.getItem(KEY) || "[]");
  } catch {
    return [];
  }
}

function write(list) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(list));
  } catch {
    /* storage full or unavailable — nothing else we can do */
  }
}

function uuid() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  return "xxxxxxxxxxxx".replace(/x/g, () => ((Math.random() * 16) | 0).toString(16));
}

export const queue = {
  list: read,
  count: () => read().length,
  clear: () => write([]),
  enqueue(opType, payload) {
    const op = { op_type: opType, client_uuid: uuid(), payload, queued_at: Date.now() };
    write([...read(), op]);
    return op;
  },
  removeByUuids(uuids) {
    const set = new Set(uuids);
    write(read().filter((op) => !set.has(op.client_uuid)));
  },
};
