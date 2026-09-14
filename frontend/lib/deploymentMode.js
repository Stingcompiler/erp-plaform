// Which product this browser is talking to: the hosted SaaS or a customer's
// own standalone server. Read once from the public health endpoint (no
// login needed) and cached for the session; the mode is fixed for the life
// of an installation, so a stale value is never wrong.
import api from "./api";

const KEY = "erp.deployment_mode.v1";
let inflight = null;

export function cachedDeploymentMode() {
  try { return sessionStorage.getItem(KEY) || null; } catch { return null; }
}

export function fetchDeploymentMode() {
  const cached = cachedDeploymentMode();
  if (cached) return Promise.resolve(cached);
  inflight ||= api
    .get("/health/")
    .then((r) => {
      const mode = r.data?.deployment_mode || "saas";
      try { sessionStorage.setItem(KEY, mode); } catch { /* ignore */ }
      return mode;
    })
    .catch(() => "saas")
    .finally(() => { inflight = null; });
  return inflight;
}
