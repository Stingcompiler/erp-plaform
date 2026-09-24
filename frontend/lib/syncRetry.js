// What a queued operation looks like after the server answered "retry": a
// temporary failure on the server's side (a deadlock, a database blip), not a
// refusal of the sale. The operation stays pending — no error, nothing for
// the cashier to discard — and is sent again after a growing pause. After
// MAX_RETRY_ATTEMPTS such answers it becomes an error after all, so an
// operation the server can never apply is not silently retried for ever.

export const RETRY_DELAYS_MS = [30_000, 120_000, 600_000, 1_800_000, 3_600_000];
export const MAX_RETRY_ATTEMPTS = 6;
export const RETRY_EXHAUSTED = "__retry_exhausted__";

// The fields to merge into the stored op for a "retry" result.
export function retryPatch(row, now = Date.now()) {
  const attempts = (Number(row?.attempts) || 0) + 1;
  if (attempts >= MAX_RETRY_ATTEMPTS) {
    return { attempts, retry_at: null, error: RETRY_EXHAUSTED, error_field: null };
  }
  const delay = RETRY_DELAYS_MS[Math.min(attempts - 1, RETRY_DELAYS_MS.length - 1)];
  return { attempts, retry_at: now + delay, error: null, error_field: null };
}

// Whether an automatic flush may send this op now.
export function isDue(op, now = Date.now()) {
  return !op?.retry_at || op.retry_at <= now;
}

// Pending, but waiting on a retry the server asked for.
export function isRetrying(op) {
  return Boolean(op && !op.error && Number(op.attempts) > 0);
}

// Items still on their way to the server: not refused, maybe waiting on a
// retry. A refused item waits for a person (repair or discard) instead.
export function waitingToSend(operations) {
  return (operations || []).filter((op) => !op?.error).length;
}

// A refusal from the commercial gate (subscription or licence) is not a
// session problem: signing in again changes nothing, renewing does.
const COMMERCIAL_CODES = new Set(["subscription_read_only", "license_read_only", "module_not_in_plan"]);
// What a failed push (no per-item answer) means for the till.
export function pushErrorKind(err) {
  const status = err?.response?.status;
  const data = err?.response?.data;
  if (status === 409) return "identity";
  if (status === 403 && COMMERCIAL_CODES.has(data?.code ?? data?.detail?.code)) return "subscription";
  if (status === 401 || status === 403) return "auth";
  return "network";
}
