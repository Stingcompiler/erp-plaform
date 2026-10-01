"use client";

// Password reset by email code (accounts/password_reset.py; no links since
// 2026-10-01): email -> 6-digit code -> new password -> done. An
// administrator's reset email opens this page on the code step with
// `?email=&challenge=` (lib/passwordReset.resetDeepLink).

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Check, Circle, KeyRound, MailX, RotateCcw } from "lucide-react";

import LogoMark from "@/components/brand/LogoMark";
import Wordmark from "@/components/brand/Wordmark";
import CodeStep from "@/components/marketing/CodeStep";
import PasswordInput from "@/components/ui/PasswordInput";
import SuccessCheck from "@/components/ui/SuccessCheck";
import { Button, Field, Input, controlClass as INPUT_CLASS } from "@/components/ui/kit";
import { auth } from "@/lib/api";
import { codeError, fieldErrors, formatCountdown } from "@/lib/otpCode";
import { passwordChecks, passwordReady, resetDeepLink } from "@/lib/passwordReset";
import { useI18n } from "../providers/I18nProvider";

const STEPS = ["email", "code", "password"];
const LINK_BUTTON = "tap inline-flex min-h-11 w-full items-center justify-center rounded-control bg-accent px-5 py-2 text-sm font-semibold text-white hover:bg-accent-strong";

function Stepper({ step, t }) {
  const index = step === "done" ? STEPS.length : STEPS.indexOf(step);
  return (
    <ol className="mb-4 flex items-center gap-2" aria-label={t("passwordReset.stepOf", { n: Math.min(index + 1, 3) })}>
      {STEPS.map((name, i) => {
        const done = i < index;
        const current = i === index;
        return (
          <li key={name} className="flex min-w-0 flex-1 items-center gap-2" aria-current={current ? "step" : undefined}>
            <span className={`grid h-6 w-6 shrink-0 place-items-center rounded-full text-xs font-bold transition-colors ${done ? "bg-ok text-white" : current ? "bg-accent text-white" : "border border-line bg-surface text-muted"}`}>
              {done ? <Check size={13} aria-hidden="true" /> : i + 1}
            </span>
            <span className={`truncate text-xs ${current ? "font-semibold text-ink" : "text-muted"}`}>{t(`passwordReset.steps.${name}`)}</span>
            {i < STEPS.length - 1 && <span className={`h-px flex-1 ${done ? "bg-ok" : "bg-line"}`} aria-hidden="true" />}
          </li>
        );
      })}
    </ol>
  );
}

function Hint({ met, children }) {
  return (
    <li className={`flex items-center gap-2 transition-colors ${met ? "text-ok" : "text-muted"}`}>
      {met ? <Check size={14} aria-hidden="true" /> : <Circle size={10} className="mx-0.5" aria-hidden="true" />}
      <span>{children}</span>
    </li>
  );
}

export default function ForgotPasswordPage() {
  const { t } = useI18n();
  const [step, setStep] = useState("email");
  const [email, setEmail] = useState("");
  const [challenge, setChallenge] = useState("");
  const [resendAfter, setResendAfter] = useState(60);
  const [token, setToken] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [touched, setTouched] = useState(false);
  const [noEmail, setNoEmail] = useState(false);
  const [emailError, setEmailError] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [expired, setExpired] = useState(false);
  const [busy, setBusy] = useState(false);
  const passwordRef = useRef(null);

  // An administrator's reset email: open on the code step, then scrub the
  // address bar so the challenge does not linger in history.
  useEffect(() => {
    const link = resetDeepLink(window.location.search);
    const params = new URLSearchParams(window.location.search);
    if (link) {
      setEmail(link.email);
      setChallenge(link.challenge);
      setStep("code");
    } else if (params.get("email")) {
      setEmail(params.get("email").slice(0, 254));
    }
    if (window.location.search) window.history.replaceState({}, "", "/forgot-password/");
  }, []);

  useEffect(() => {
    if (step === "password") passwordRef.current?.focus();
  }, [step]);

  async function requestCode(event) {
    event.preventDefault();
    const value = email.trim();
    if (!/^\S+@\S+\.\S+$/.test(value)) return setEmailError(t("passwordReset.invalidEmail"));
    setEmailError("");
    setBusy(true);
    try {
      const { data } = await auth.requestPasswordReset(value);
      if (!data.email_enabled) {
        setNoEmail(true);
        return;
      }
      setChallenge(data.challenge_id);
      setResendAfter(Number(data.resend_after) || 60);
      setExpired(false);
      setStep("code");
    } catch (failure) {
      const parsed = codeError(failure);
      if (parsed.code === "too_many_codes" || parsed.code === "throttled") {
        setEmailError(t("passwordReset.tooMany", { time: formatCountdown(parsed.retryAfter || 3600) }));
      } else if (parsed.code === "invalid") {
        setEmailError(t("passwordReset.invalidEmail"));
      } else if (parsed.code === "email_unavailable") {
        setEmailError(t("passwordReset.emailUnavailable"));
      } else {
        setEmailError(t("passwordReset.failed"));
      }
    } finally {
      setBusy(false);
    }
  }

  async function verifyCode(code) {
    const { data } = await auth.verifyPasswordReset(challenge, code);
    setToken(data.reset_token);
    setPassword("");
    setConfirm("");
    setTouched(false);
    setPasswordError("");
    setStep("password");
  }

  async function resendCode() {
    const { data } = await auth.resendPasswordReset(challenge);
    return data.resend_after;
  }

  function startOver() {
    setStep("email");
    setChallenge("");
    setToken("");
    setExpired(false);
    setPasswordError("");
  }

  const checks = passwordChecks(password, confirm);
  const mismatch = touched && confirm.length > 0 && !checks.match;

  async function setNewPassword(event) {
    event.preventDefault();
    setTouched(true);
    if (!passwordReady(checks)) return;
    setBusy(true);
    setPasswordError("");
    try {
      await auth.confirmPasswordReset(token, password);
      setStep("done");
    } catch (failure) {
      const parsed = codeError(failure);
      if (parsed.code === "reset_expired" || parsed.code === "link_flow_retired") {
        setExpired(true);
      } else if (parsed.code === "invalid") {
        setPasswordError(fieldErrors(parsed.fields).password || t("passwordReset.failed"));
        passwordRef.current?.focus();
      } else if (parsed.code === "throttled") {
        setPasswordError(t("passwordReset.tooMany", { time: formatCountdown(parsed.retryAfter || 60) }));
      } else {
        setPasswordError(t("passwordReset.failed"));
      }
    } finally {
      setBusy(false);
    }
  }

  const card = "enter-rise rounded-card border border-line bg-surface p-6 shadow-card sm:p-8";

  return (
    <main className="flex min-h-screen items-center justify-center bg-paper px-4 py-8 sm:p-6">
      <div className="w-full min-w-0 max-w-md">
        <Link href="/" className="mb-6 inline-flex items-center gap-2 font-display text-lg font-bold">
          <LogoMark size={36} decorative />
          <Wordmark />
        </Link>

        {!noEmail && <Stepper step={step} t={t} />}

        {noEmail ? (
          <section key="no-email" className={`${card} text-center`}>
            <MailX className="mx-auto text-warn" size={44} aria-hidden="true" />
            <h1 className="mt-4 font-display text-2xl font-semibold">{t("passwordReset.noEmailTitle")}</h1>
            <p className="mt-2 text-sm text-muted">{t("passwordReset.noEmailBody")}</p>
            <Link href="/login" className={`${LINK_BUTTON} mt-6`}>{t("passwordReset.backToLogin")}</Link>
          </section>
        ) : step === "email" ? (
          <section key="email" className={card}>
            <form onSubmit={requestCode} noValidate>
              <KeyRound className="mb-4 text-accent" size={32} aria-hidden="true" />
              <h1 className="font-display text-2xl font-semibold">{t("passwordReset.title")}</h1>
              <p className="mt-2 text-sm text-muted">{t("passwordReset.subtitle")}</p>
              <div className="mt-6 space-y-4">
                <Field label={t("auth.emailLabel")} error={emailError}>
                  <Input
                    type="email"
                    inputMode="email"
                    autoComplete="username"
                    dir="ltr"
                    value={email}
                    onChange={(e) => { setEmail(e.target.value); if (emailError) setEmailError(""); }}
                    required
                    autoFocus
                  />
                </Field>
                <Button type="submit" className="w-full" disabled={busy || !email.trim()}>
                  {busy ? t("passwordReset.sending") : t("passwordReset.send")}
                </Button>
                <Link href="/login" className="block text-center text-sm text-muted hover:text-ink">{t("passwordReset.backToLogin")}</Link>
              </div>
            </form>
          </section>
        ) : step === "code" ? (
          <CodeStep
            key={`code-${challenge}`}
            className="bg-surface"
            title={t("passwordReset.codeTitle")}
            sentText={t("passwordReset.codeSent", { email: email.trim() })}
            resendAfter={resendAfter}
            onVerify={verifyCode}
            onResend={resendCode}
            onBack={startOver}
            backLabel={t("passwordReset.changeEmail")}
          />
        ) : step === "password" ? (
          <section key="password" className={card}>
            {expired ? (
              <div className="text-center" role="alert">
                <RotateCcw className="mx-auto text-warn" size={40} aria-hidden="true" />
                <p className="mt-4 text-sm text-ink">{t("passwordReset.expired")}</p>
                <Button className="mt-6 w-full" onClick={startOver}>{t("passwordReset.startOver")}</Button>
              </div>
            ) : (
              <form onSubmit={setNewPassword} noValidate>
                <h1 className="font-display text-2xl font-semibold">{t("passwordReset.newTitle")}</h1>
                <p className="mt-2 text-sm text-muted">{t("passwordReset.newSubtitle")}</p>
                {/* Lets the browser's password manager file the new password under the right account. */}
                <input type="email" autoComplete="username" value={email} readOnly hidden />
                <div className="mt-6 space-y-4">
                  <Field label={t("passwordReset.newPassword")} error={passwordError}>
                    <PasswordInput
                      ref={passwordRef}
                      autoComplete="new-password"
                      minLength={10}
                      value={password}
                      onChange={(e) => { setPassword(e.target.value); if (passwordError) setPasswordError(""); }}
                      required
                      className={INPUT_CLASS}
                    />
                  </Field>
                  <Field label={t("passwordReset.confirmPassword")} error={mismatch ? t("passwordReset.mismatch") : ""}>
                    <PasswordInput
                      autoComplete="new-password"
                      minLength={10}
                      value={confirm}
                      onChange={(e) => setConfirm(e.target.value)}
                      onBlur={() => setTouched(true)}
                      required
                      className={INPUT_CLASS}
                    />
                  </Field>
                  <div className="rounded-control border border-line bg-paper p-3 text-sm">
                    <p className="mb-2 text-xs font-semibold text-muted">{t("passwordReset.hints.title")}</p>
                    <ul className="space-y-1.5">
                      <Hint met={checks.length}>{t("passwordReset.hints.length")}</Hint>
                      <Hint met={checks.notNumeric}>{t("passwordReset.hints.notNumeric")}</Hint>
                      <Hint met={checks.mix}>{t("passwordReset.hints.mix")}</Hint>
                      <Hint met={checks.match}>{t("passwordReset.hints.match")}</Hint>
                    </ul>
                  </div>
                  <Button type="submit" className="w-full" disabled={busy || !passwordReady(checks)}>
                    {busy ? t("common.saving") : t("passwordReset.setPassword")}
                  </Button>
                </div>
              </form>
            )}
          </section>
        ) : (
          <section key="done" className={`${card} text-center`}>
            <SuccessCheck size={56} className="mx-auto" label={t("passwordReset.doneTitle")} />
            <h1 className="mt-4 font-display text-2xl font-semibold">{t("passwordReset.doneTitle")}</h1>
            <p className="mt-2 text-sm text-muted">{t("passwordReset.doneBody")}</p>
            <Link href="/login" className={`${LINK_BUTTON} mt-6`}>{t("passwordReset.signIn")}</Link>
          </section>
        )}

        {(step === "code" || step === "password") && !noEmail && (
          <Link href="/login" className="mt-4 block text-center text-sm text-muted hover:text-ink">{t("passwordReset.backToLogin")}</Link>
        )}
      </div>
    </main>
  );
}
