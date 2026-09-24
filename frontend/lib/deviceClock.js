// How wrong this device's clock is, measured against the server.
//
// Cheap tablets lose their clock after a power cut and fix it (or break it
// again) when the network comes back. The server corrects queued times by
// the gap it sees at upload, but by then the clock may be a different
// clock from the one that stamped the sale. So the gap is measured every
// time the reachability probe gets an answer, and each queued item carries
// the gap as it was when the item was captured (`clock_offset_ms`); the
// server prefers that one.
//
// offset = server time - device time, in milliseconds. A device property,
// shared by every account on this browser.

const KEY = "erp.clock.v1";

// `serverTime` from the server's answer; `sentAt`/`receivedAt` are this
// device's Date.now() around the request, so half the round trip is
// credited to each direction.
export function recordServerTime(serverTime, sentAt, receivedAt = Date.now()) {
  const server = Date.parse(serverTime);
  if (!Number.isFinite(server) || !Number.isFinite(sentAt)) return null;
  const offset = Math.round(server - (sentAt + receivedAt) / 2);
  try { localStorage.setItem(KEY, JSON.stringify({ offset_ms: offset, measured_at: receivedAt })); }
  catch { /* private mode: the upload-time correction still applies */ }
  return offset;
}

// The last measured offset, or null when this device never reached a
// server that reports its time.
export function clockOffset() {
  try {
    const row = JSON.parse(localStorage.getItem(KEY) || "null");
    return Number.isFinite(row?.offset_ms) ? row.offset_ms : null;
  } catch {
    return null;
  }
}
