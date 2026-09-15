// Install-to-device state for the app shell.
//
// Why this matters beyond a home-screen icon: browsers only grant durable
// storage (`navigator.storage.persist()`) generously to an INSTALLED app.
// A plain tab's IndexedDB/localStorage is "best effort" — Safari evicts it
// after seven days without use and Chromium under disk pressure — and that
// is where the queued offline sales live. So "install" is part of keeping a
// sale safe, not cosmetics, and the UI says so.
//
// `beforeinstallprompt` only fires in Chromium browsers. Safari/Firefox
// install through their own share/menu, so the button is hidden there and
// the drawer explains the manual route instead.

import { useEffect, useState } from "react";

let deferredPrompt = null;
const listeners = new Set();

function notify() {
  listeners.forEach((fn) => fn());
}

if (typeof window !== "undefined") {
  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    deferredPrompt = event;
    notify();
  });
  window.addEventListener("appinstalled", () => {
    deferredPrompt = null;
    notify();
  });
}

export function isStandaloneDisplay() {
  if (typeof window === "undefined") return false;
  return (
    window.matchMedia?.("(display-mode: standalone)")?.matches ||
    window.navigator.standalone === true // iOS Safari
  );
}

export async function isStoragePersisted() {
  try {
    return (await navigator.storage?.persisted?.()) ?? false;
  } catch {
    return false;
  }
}

export function useInstallPrompt() {
  const [, force] = useState(0);
  useEffect(() => {
    const fn = () => force((n) => n + 1);
    listeners.add(fn);
    const media = window.matchMedia?.("(display-mode: standalone)");
    media?.addEventListener?.("change", fn);
    return () => {
      listeners.delete(fn);
      media?.removeEventListener?.("change", fn);
    };
  }, []);

  const installed = isStandaloneDisplay();
  const canPrompt = Boolean(deferredPrompt) && !installed;

  const prompt = async () => {
    if (!deferredPrompt) return "unavailable";
    const event = deferredPrompt;
    deferredPrompt = null;
    notify();
    try {
      event.prompt();
      const { outcome } = await event.userChoice;
      return outcome; // "accepted" | "dismissed"
    } catch {
      return "dismissed";
    }
  };

  return { installed, canPrompt, prompt };
}
