"use client";

// The email-code step shared by the trial form and vezano.app/track/: one
// field for the 6 digits (numeric keypad, the OS's one-time-code autofill,
// paste of "123 456" or Arabic digits), a resend link with its countdown,
// and errors next to the field. The parent owns the API calls: `onVerify`
// and `onResend` throw the axios error, which lib/otpCode reads.

import { useEffect, useId, useRef, useState } from "react";
import { MailCheck, RotateCw } from "lucide-react";

import { useI18n } from "@/app/providers/I18nProvider";
import { CODE_LENGTH, codeError, formatCountdown, isCompleteCode, normaliseCode, secondsUntil } from "@/lib/otpCode";

export function codeErrorText(t, error) {
  if (!error) return "";
  if (error.code === "wrong_code" && error.attemptsLeft > 0) {
    return t("otp.errors.wrongCodeLeft", { left: error.attemptsLeft });
  }
  if (error.code === "resend_cooldown" || error.code === "too_many_codes") {
    return t(`otp.errors.${error.code}`, { time: formatCountdown(error.retryAfter || 60) });
  }
  const key = `otp.errors.${error.code}`;
  const text = t(key);
  return text === key ? t("otp.errors.network") : text;
}

export default function CodeStep({
  title, sentText, onVerify, onResend, resendAfter = 60, onBack, backLabel, children,
  className = "bg-paper",
}) {
  const { t } = useI18n();
  const id = useId();
  const input = useRef(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState("");
  const [resendAt, setResendAt] = useState(() => Date.now() + resendAfter * 1000);
  const [now, setNow] = useState(() => Date.now());
  const wait = secondsUntil(resendAt, now);

  useEffect(() => { input.current?.focus(); }, []);
  useEffect(() => {
    if (wait <= 0) return undefined;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [wait]);

  async function submit(value) {
    const digits = normaliseCode(value);
    if (busy) return;
    if (!isCompleteCode(digits)) {
      setError({ code: "incomplete" });
      input.current?.focus();
      return;
    }
    setBusy(true); setError(null); setNotice("");
    try {
      await onVerify(digits);
    } catch (failure) {
      const parsed = codeError(failure);
      setError(parsed);
      if (parsed.code === "wrong_code") setCode("");
      input.current?.focus();
    } finally {
      setBusy(false);
    }
  }

  async function resend() {
    if (busy || wait > 0) return;
    setBusy(true); setError(null); setNotice("");
    try {
      const after = await onResend();
      setResendAt(Date.now() + (Number(after) || resendAfter) * 1000);
      setNow(Date.now());
      setCode("");
      setNotice(t("otp.resent"));
      input.current?.focus();
    } catch (failure) {
      const parsed = codeError(failure);
      setError(parsed);
      if (parsed.retryAfter) { setResendAt(Date.now() + parsed.retryAfter * 1000); setNow(Date.now()); }
    } finally {
      setBusy(false);
    }
  }

  function onChange(event) {
    const digits = normaliseCode(event.target.value);
    setCode(digits);
    if (error) setError(null);
    // A pasted or autofilled code goes straight through.
    if (digits.length === CODE_LENGTH && digits !== code) submit(digits);
  }

  const errorText = codeErrorText(t, error);
  const dead = error && (error.code === "code_expired" || error.code === "too_many_attempts");

  return (
    <div className={`enter-rise rounded-card border border-line p-6 shadow-card sm:p-8 ${className}`}>
      <div className="flex items-start gap-3">
        <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-accent/10 text-accent">
          <MailCheck size={22} aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <h2 className="font-display text-xl font-semibold">{title || t("otp.title")}</h2>
          <p className="mt-1 break-words text-sm text-muted">{sentText}</p>
        </div>
      </div>

      <form
        className="mt-6"
        noValidate
        onSubmit={(event) => { event.preventDefault(); submit(code); }}
      >
        <label htmlFor={`${id}-code`} className="mb-1.5 block text-sm font-medium text-ink">{t("otp.label")}</label>
        <div className="flex flex-col gap-2 sm:flex-row">
          <input
            ref={input}
            id={`${id}-code`}
            name="one-time-code"
            value={code}
            onChange={onChange}
            inputMode="numeric"
            autoComplete="one-time-code"
            pattern="[0-9]*"
            maxLength={CODE_LENGTH + 6}
            dir="ltr"
            placeholder="••••••"
            aria-invalid={error ? "true" : undefined}
            aria-describedby={`${id}-help${errorText ? ` ${id}-error` : ""}`}
            disabled={busy && !error}
            className={`tabular min-w-0 flex-1 rounded-control border bg-surface px-3 py-3 text-center font-mono text-2xl font-bold tracking-[0.5em] text-ink outline-none placeholder:text-muted focus:border-accent focus-visible:ring-2 focus-visible:ring-accent/40 ${error ? "border-danger" : "border-line"}`}
          />
          <button
            type="submit"
            disabled={busy || dead}
            className="rounded-control bg-accent px-6 py-3 font-medium text-white hover:bg-accent-strong disabled:opacity-50"
          >
            {busy ? t("otp.verifying") : t("otp.verify")}
          </button>
        </div>
        {errorText && (
          <p id={`${id}-error`} role="alert" className="mt-2 text-sm text-danger">{errorText}</p>
        )}
        {notice && !errorText && <p role="status" className="mt-2 text-sm text-ok">{notice}</p>}
        <p id={`${id}-help`} className="mt-2 text-xs text-muted">{t("otp.help")}</p>
      </form>

      <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4 text-sm">
        <button
          type="button"
          onClick={resend}
          disabled={busy || wait > 0}
          className="inline-flex min-h-11 items-center gap-2 font-medium text-accent hover:underline disabled:cursor-not-allowed disabled:text-muted disabled:no-underline"
        >
          <RotateCw size={15} aria-hidden="true" />
          {wait > 0 ? t("otp.resendIn", { time: formatCountdown(wait) }) : t("otp.resend")}
        </button>
        {onBack && (
          <button type="button" onClick={onBack} className="min-h-11 font-medium text-muted hover:text-ink hover:underline">
            {backLabel}
          </button>
        )}
      </div>
      {children}
    </div>
  );
}
