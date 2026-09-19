"use client";

import { useEffect, useState } from "react";
import { BellRing, BellOff } from "lucide-react";

import { Button } from "@/components/ui/kit";
import { pushStatus, subscribeToPush, unsubscribeFromPush } from "@/lib/push";
import { useI18n } from "../../app/providers/I18nProvider";

// One line above the orders list: turn phone notifications for new orders
// on or off for this browser. Silent when the browser cannot do push or the
// server has no VAPID key — the badge and the email still work.
export default function PushPrompt() {
  const { t } = useI18n();
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = () => pushStatus().then(setStatus).catch(() => setStatus(null));
  useEffect(() => { load(); }, []);

  if (!status?.supported || !status.enabled) return null;
  const toggle = async () => {
    setBusy(true); setError("");
    try {
      if (status.subscribed) await unsubscribeFromPush();
      else {
        const res = await subscribeToPush(status.publicKey);
        if (!res.ok) setError(t(res.permission === "denied" ? "webOrders.pushDenied" : "webOrders.pushRefused"));
      }
      await load();
    } catch { setError(t("webOrders.pushError")); }
    finally { setBusy(false); }
  };
  return (
    <div className="mb-4 flex flex-wrap items-center gap-3 rounded-control border border-line bg-surface px-4 py-3 text-sm">
      {status.subscribed ? <BellRing size={18} className="text-ok" /> : <BellOff size={18} className="text-muted" />}
      <span className="flex-1">{status.subscribed ? t("webOrders.pushOn") : t("webOrders.pushOff")}</span>
      {error && <span className="text-danger">{error}</span>}
      <Button variant={status.subscribed ? "outline" : "primary"} disabled={busy} onClick={toggle}>
        {status.subscribed ? t("webOrders.pushDisable") : t("webOrders.pushEnable")}
      </Button>
    </div>
  );
}
