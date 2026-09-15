// Registers the app-shell worker in production builds only: in `next dev`
// a cached shell would fight hot reload and mask real errors.
//
// Also owns the UPDATE handshake. The worker never activates a new build on
// its own (see public/sw.js); it sits in `waiting` until the page sends
// SKIP_WAITING. The page only does that when nothing would be lost by the
// reload that follows: the sync queue is empty, the server is reachable and
// the caller (the sync layer) says the screen holds no unsaved work.
import { useEffect, useState } from "react";

const UPDATE_CHECK_INTERVAL_MS = 60 * 60 * 1000;

let waiting = null;
let reloading = false;
const listeners = new Set();
const notify = () => listeners.forEach((fn) => fn());

function watch(registration) {
  const track = () => {
    if (registration.waiting && navigator.serviceWorker.controller) {
      waiting = registration.waiting;
      notify();
    }
  };
  track();
  registration.addEventListener("updatefound", () => {
    const installing = registration.installing;
    installing?.addEventListener("statechange", track);
  });
  // A till stays open for days; without this it would only learn about a
  // deploy on its next full reload.
  setInterval(() => registration.update().catch(() => {}), UPDATE_CHECK_INTERVAL_MS);
}

export function registerServiceWorker() {
  if (typeof window === "undefined" || !("serviceWorker" in navigator)) return;
  if (process.env.NODE_ENV !== "production") return;
  const register = () => {
    navigator.serviceWorker.register("/sw.js").then(watch).catch(() => {
      /* an unregistered worker only means no offline shell; never block the app */
    });
  };
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    // Only reload for a takeover we asked for; the very first install also
    // fires this and must not bounce the page under the cashier.
    if (!reloading) return;
    window.location.reload();
  });
  // React mounts after the window has finished loading, so waiting for the
  // "load" event here would wait forever; register now once it has fired.
  if (document.readyState === "complete") register();
  else window.addEventListener("load", register, { once: true });
}

export function updateAvailable() {
  return Boolean(waiting);
}

// Hand over to the waiting build and reload once it controls the page.
export function applyUpdate() {
  if (!waiting) return false;
  reloading = true;
  waiting.postMessage({ type: "SKIP_WAITING" });
  waiting = null;
  notify();
  return true;
}

export function useServiceWorkerUpdate() {
  const [, force] = useState(0);
  useEffect(() => {
    const fn = () => force((n) => n + 1);
    listeners.add(fn);
    return () => listeners.delete(fn);
  }, []);
  return { updateReady: Boolean(waiting), applyUpdate };
}
