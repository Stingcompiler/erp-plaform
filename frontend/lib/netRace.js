// The till's lookups (barcode scan, product search) against a network that
// accepts the connection and never answers — a router with no upstream, the
// common failure where this runs. They went network-first with no deadline:
// the scan sat on "Looking up…" for ever, and every later scan queued behind
// it. Now a lookup gets NETWORK_DEADLINE_MS; past that it is abandoned
// (aborted) and the caller answers from the local catalogue. After one
// timeout the network is "suspect" for a while and lookups go to the local
// catalogue first, so a burst of scans does not wait out a deadline each.
export const NETWORK_DEADLINE_MS = 3500;
export const SUSPECT_FOR_MS = 20000;

let suspectUntil = 0;

export function networkSuspect(now = Date.now()) {
  return now < suspectUntil;
}

export function markNetworkSuspect(now = Date.now()) {
  suspectUntil = now + SUSPECT_FOR_MS;
}

export function clearNetworkSuspect() {
  suspectUntil = 0;
}

// Runs `request(signal)` with a deadline. Rejects with an error that has no
// `response` (like any network failure) and `timedOut: true` when the
// deadline passes first; the request itself is aborted.
export function raceNetwork(request, { ms = NETWORK_DEADLINE_MS } = {}) {
  const controller = typeof AbortController !== "undefined" ? new AbortController() : null;
  let timer;
  const deadline = new Promise((_resolve, reject) => {
    timer = setTimeout(() => {
      controller?.abort();
      markNetworkSuspect();
      const error = new Error("The server did not answer in time.");
      error.timedOut = true;
      error.code = "ECONNABORTED";
      reject(error);
    }, ms);
  });
  const call = Promise.resolve().then(() => request(controller?.signal)).then((result) => {
    // A remembered answer (lib/responseCache, `stale`) says nothing about
    // the network being back.
    if (!result?.stale) clearNetworkSuspect();
    return result;
  });
  return Promise.race([call, deadline]).finally(() => clearTimeout(timer));
}
