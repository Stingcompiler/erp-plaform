"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ScanLine } from "lucide-react";

import { inventory } from "@/lib/api";
import { useI18n } from "../../app/providers/I18nProvider";
import { cacheProducts, findProductOffline } from "@/lib/productCache";
import { Input } from "@/components/ui/kit";

// A UPC-A label is 12 digits; the same article in an EAN-13 catalogue is the
// same digits with a leading 0, and some scanners drop that 0. The server does
// the same widening for online lookups; this covers the offline cache.
export function scanCandidates(raw) {
  const code = String(raw || "").trim();
  if (!code) return [];
  const out = [code];
  if (/^\d+$/.test(code)) {
    if (code.length === 12) out.push(`0${code}`);
    else if (code.length === 13 && code.startsWith("0")) out.push(code.slice(1));
  }
  return out;
}

/**
 * Barcode entry for handheld scanners.
 *
 * Nearly all scanners present as an HID keyboard: they "type" the code then
 * send Enter (some are configured for Tab). So this is deliberately just a
 * focused text input that resolves on the terminator — no drivers, no browser
 * permissions, and it doubles as manual entry.
 *
 * Two things a scanner needs that a plain input does not give:
 *  - it must keep the focus. Disabling the field during the lookup dropped the
 *    focus, and the next burst from the scanner went to the page body and was
 *    lost; the field now stays enabled and consecutive scans queue up.
 *  - with `captureGlobal`, keystrokes that arrive while nothing editable is
 *    focused are routed here, so a cashier who just clicked a button can keep
 *    scanning without finding the box again.
 *
 * Lookup is exact-match (never the fuzzy product search), and falls back to the
 * locally cached catalogue when offline so POS keeps scanning during an outage
 * (PROJECT_RULES Rule #2).
 */
export default function BarcodeScanInput({ onScan, autoFocus = true, disabled, captureGlobal = false }) {
  const { t } = useI18n();
  const [code, setCode] = useState("");
  const [status, setStatus] = useState(null); // {tone, text}
  const ref = useRef(null);
  const queue = useRef(Promise.resolve());

  useEffect(() => {
    if (autoFocus && !disabled) ref.current?.focus();
  }, [autoFocus, disabled]);

  const lookup = useCallback(
    async (value) => {
      setStatus({ tone: "muted", text: t("inventory.scanning") });
      try {
        const res = await inventory.byBarcode(value);
        cacheProducts([res.data]);
        onScan(res.data);
        setStatus({ tone: "ok", text: t("inventory.scanFound", { name: res.data.name }) });
      } catch (err) {
        // Offline (no response at all) → try the cached catalogue before failing.
        if (!err?.response) {
          for (const candidate of scanCandidates(value)) {
            const cached = await findProductOffline(candidate);
            if (cached) {
              onScan(cached);
              setStatus({ tone: "warn", text: t("inventory.scanOffline") });
              return;
            }
          }
        }
        setStatus({ tone: "danger", text: t("inventory.scanNotFound", { code: value }) });
      }
    },
    [onScan, t]
  );

  const resolve = useCallback(
    (raw) => {
      const value = raw.trim();
      setCode("");
      if (!value) return;
      // Scans are serialised, not dropped: a second beep before the first
      // lookup answered still rings up the second item, in order.
      queue.current = queue.current.then(() => lookup(value));
    },
    [lookup]
  );

  useEffect(() => {
    if (!captureGlobal || disabled) return undefined;
    const editable = (el) =>
      el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable);
    const onKey = (e) => {
      if (e.ctrlKey || e.metaKey || e.altKey || e.key.length !== 1) return;
      if (editable(document.activeElement)) return;
      const el = ref.current;
      if (!el) return;
      // The first character of a burst lands here; the rest follow through the
      // focused input as normal keystrokes.
      e.preventDefault();
      el.focus();
      setCode((c) => c + e.key);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [captureGlobal, disabled]);

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
          disabled={disabled}
          onChange={(e) => setCode(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || (e.key === "Tab" && code.trim())) {
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
