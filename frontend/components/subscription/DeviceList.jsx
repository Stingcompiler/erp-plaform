"use client";

import { useState } from "react";
import { MonitorSmartphone, Pencil, Trash2 } from "lucide-react";

import { Badge, Button, Input } from "@/components/ui/kit";
import { useI18n } from "../../app/providers/I18nProvider";

function describeAgent(agent) {
  const ua = agent || "";
  const os = /iPhone|iPad/.test(ua) ? "iOS" : /Android/.test(ua) ? "Android" : /Windows/.test(ua) ? "Windows" : /Mac OS/.test(ua) ? "macOS" : /Linux/.test(ua) ? "Linux" : "";
  const browser = /Edg\//.test(ua) ? "Edge" : /Chrome\//.test(ua) ? "Chrome" : /Safari\//.test(ua) ? "Safari" : /Firefox\//.test(ua) ? "Firefox" : "";
  return [os, browser].filter(Boolean).join(" · ");
}

// Every browser that has signed in to the company. `onLabel` is optional —
// the platform team reads labels but does not write them.
export default function DeviceList({ devices, onLabel, onRevoke, onReactivate, onRemove, busyId }) {
  const { t, language } = useI18n();
  const [editing, setEditing] = useState(null);
  const [draft, setDraft] = useState("");
  const fmt = (value) => value ? new Date(value).toLocaleString(language === "ar" ? "ar" : "en", { dateStyle: "medium", timeStyle: "short" }) : "—";

  if (!devices?.length) return <p className="text-sm text-muted">{t("devices.empty")}</p>;
  return (
    <ul className="divide-y divide-line">
      {devices.map((d) => (
        <li key={d.id} className={`flex flex-wrap items-center gap-3 py-3 ${d.is_active ? "" : "opacity-60"}`}>
          <MonitorSmartphone size={18} className="shrink-0 text-muted" />
          <div className="min-w-0 flex-1">
            {editing === d.id ? (
              <form className="flex gap-2" onSubmit={async (e) => { e.preventDefault(); await onLabel(d.id, draft); setEditing(null); }}>
                <Input autoFocus maxLength={80} value={draft} onChange={(e) => setDraft(e.target.value)} placeholder={t("devices.labelPlaceholder")} />
                <Button type="submit">{t("common.save")}</Button>
                <Button type="button" variant="ghost" onClick={() => setEditing(null)}>{t("common.cancel")}</Button>
              </form>
            ) : (
              <div className="flex items-center gap-2">
                <span className="font-medium">{d.label || t("devices.unnamed", { id: d.device_id })}</span>
                {onLabel && d.is_active && (
                  <button type="button" className="text-muted hover:text-ink" onClick={() => { setEditing(d.id); setDraft(d.label || ""); }} aria-label={t("devices.rename")}>
                    <Pencil size={14} />
                  </button>
                )}
                {!d.is_active && <Badge tone="muted">{t("devices.revoked")}</Badge>}
              </div>
            )}
            <div className="mt-0.5 text-xs text-muted">
              {describeAgent(d.user_agent) || d.device_id}
              {d.branch_name && <> · {d.branch_name}</>}
              {d.last_user_name && <> · {d.last_user_name}</>}
              <> · {t("devices.lastSeen")} {fmt(d.last_seen_at)}</>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {d.is_active
              ? onRevoke && <Button variant="outline" disabled={busyId === d.id} onClick={() => onRevoke(d)}>{t("devices.revoke")}</Button>
              : onReactivate && <Button variant="outline" disabled={busyId === d.id} onClick={() => onReactivate(d)}>{t("devices.allowAgain")}</Button>}
            {onRemove && (
              <Button variant="danger" disabled={busyId === d.id} onClick={() => onRemove(d)}>
                <Trash2 size={15} />{t("devices.remove")}
              </Button>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}
