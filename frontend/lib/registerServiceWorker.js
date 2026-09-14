// Registers the app-shell worker in production builds only: in `next dev`
// a cached shell would fight hot reload and mask real errors.
export function registerServiceWorker() {
  if (typeof window === "undefined" || !("serviceWorker" in navigator)) return;
  if (process.env.NODE_ENV !== "production") return;
  const register = () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {
      /* an unregistered worker only means no offline shell; never block the app */
    });
  };
  // React mounts after the window has finished loading, so waiting for the
  // "load" event here would wait forever; register now once it has fired.
  if (document.readyState === "complete") register();
  else window.addEventListener("load", register, { once: true });
}
