// Which manual route (if any) this browser offers. `beforeinstallprompt`
// covers Chromium; everything else is a fixed fact of the browser, and
// telling a desktop Firefox user to look for a menu item that Mozilla
// removed in 2021 only makes the app look broken.
export function installRoute(ua = typeof navigator === "undefined" ? "" : navigator.userAgent) {
  if (!ua) return "unknown";
  const ios = /iPhone|iPad|iPod/.test(ua);
  const android = /Android/.test(ua);
  if (/Firefox\//.test(ua) && !/Seamonkey/.test(ua)) return android ? "firefox-android" : "firefox-desktop";
  if (/Safari\//.test(ua) && !/Chrome|Chromium|CriOS|Edg\//.test(ua)) return ios ? "safari-ios" : "safari-mac";
  return "chromium";
}

