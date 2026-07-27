"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ScanLine } from "lucide-react";

import { inventory } from "@/lib/api";
import { useI18n } from "../../app/providers/I18nProvider";
import { findCachedByBarcode } from "@/lib/productCache";
import { Input } from "@/components/ui/kit";

/**
 * Barcode entry for handheld scanners.
 *
 * Nearly all scanners present as an HID keyboard: they "type" the code then
 * send Enter. So this is deliberately just a focused text input that resolves
 * on Enter — no drivers, no browser permissions, and it doubles as manual entry.
 *
 * Lookup is exact-match (never the fuzzy product search), and falls back to the
 * locally cached catalogue when offline so POS keeps scanning during an outage
 * (PROJECT_RULES Rule #2).
 */
export default function BarcodeScanInput({ onScan, autoFocus = true, disabled }) {
  const { t } = useI18n();
  const [code, setCode] = useState("");
  const [status, setStatus] = useState(null); // {tone, text}
  const [busy, setBusy] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (autoFocus && !disabled) ref.current?.focus();
  }, [autoFocus, disabled]);

  const resolve = useCallback(
    async (raw) => {
      const value = raw.trim();
      if (!value) return;
      setBusy(true);
      setStatus({ tone: "muted", text: t("inventory.scanning") });
      try {
        const res = await inventory.byBarcode(value);
        onScan(res.data);
        setStatus({ tone: "ok", text: t("inventory.scanFound", { name: res.data.name }) });
      } catch (err) {
        // Offline (no response at all) → try the cached catalogue before failing.
        if (!err?.response) {
          const cached = findCachedByBarcode(value);
          if (cached) {
            onScan(cached);
            setStatus({ tone: "warn", text: t("inventory.scanOffline") });
            setCode("");
            setBusy(false);
            ref.current?.focus();
            return;
          }
        }
        setStatus({ tone: "danger", text: t("inventory.scanNotFound", { code: value }) });
      } finally {
        setCode("");
        setBusy(false);
        // Refocus so consecutive scans need no clicking.
        ref.current?.focus();
      }
    },
    [onScan, t]
  );

  const toneClass = {
    ok: "text-ok",
    warn: "text-warn",
    danger: "text-danger",
    muted: "text-muted",
  };

  return (
    <div>
      <div className="relative">
        <ScanLine
          size={16}
          className="pointer-events-none absolute inset-y-0 start-3 my-auto text-accent"
        />
        <Input
          ref={ref}
          value={code}
          disabled={disabled || busy}
          onChange={(e) => setCode(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              resolve(code);
            }
          }}
          placeholder={t("inventory.scan")}
          className="ps-9"
          inputMode="numeric"
          autoComplete="off"
        />
      </div>
      <p className={`mt-1 text-xs ${status ? toneClass[status.tone] : "text-muted"}`}>
        {status ? status.text : t("inventory.scanHint")}
      </p>
    </div>
  );
}
