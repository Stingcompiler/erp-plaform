// Web Push on the client: ask the browser, hand the subscription to the
// server. Everything here is optional — a browser without push (iOS Safari
// outside the home-screen app, or a user who said no) just keeps the badge
// and the email.
import api from "./api";

function urlBase64ToUint8Array(base64) {
  const padding = "=".repeat((4 - (base64.length % 4)) % 4);
  const raw = atob((base64 + padding).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

export function pushSupported() {
  return typeof window !== "undefined" && "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

export async function pushStatus() {
  if (!pushSupported()) return { supported: false, enabled: false, subscribed: false, permission: "unsupported" };
  const { data } = await api.get("/push/subscription/");
  const reg = await navigator.serviceWorker.ready;
  const sub = await reg.pushManager.getSubscription();
  return { supported: true, enabled: data.enabled, publicKey: data.public_key, subscribed: Boolean(sub), permission: Notification.permission };
}

export async function subscribeToPush(publicKey) {
  const permission = await Notification.requestPermission();
  if (permission !== "granted") return { ok: false, permission };
  const reg = await navigator.serviceWorker.ready;
  const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlBase64ToUint8Array(publicKey) });
  const json = sub.toJSON();
  await api.post("/push/subscription/", { endpoint: json.endpoint, keys: json.keys });
  return { ok: true, permission };
}

export async function unsubscribeFromPush() {
  const reg = await navigator.serviceWorker.ready;
  const sub = await reg.pushManager.getSubscription();
  if (!sub) return;
  await api.delete("/push/subscription/", { data: { endpoint: sub.endpoint } });
  await sub.unsubscribe();
}
