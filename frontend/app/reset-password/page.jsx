"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { CheckCircle2, KeyRound } from "lucide-react";

import LogoMark from "@/components/brand/LogoMark";
import Wordmark from "@/components/brand/Wordmark";
import PasswordInput from "@/components/ui/PasswordInput";
import { Button, Field, controlClass as INPUT_CLASS } from "@/components/ui/kit";
import { auth } from "@/lib/api";
import { useI18n } from "../providers/I18nProvider";
import { errorText } from "@/lib/errors";

export default function ResetPasswordPage() {
  const { t } = useI18n();
  const [uid, setUid] = useState("");
  const [token, setToken] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  // Read once, then scrub from the address bar (same as owner activation):
  // a reset token must not linger in history or travel with a pasted URL.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const u = params.get("uid");
    const k = params.get("token");
    if (!u || !k) return;
    setUid(u);
    setToken(k);
    window.history.replaceState({}, "", "/reset-password/");
  }, []);

  async function submit(event) {
    event.preventDefault();
    setError("");
    if (!uid || !token) return setError(t("passwordReset.missingToken"));
    if (password !== confirm) return setError(t("ownerActivation.mismatch"));
    setBusy(true);
    try {
      await auth.confirmPasswordReset(uid, token, password);
      setDone(true);
    } catch (err) {
      setError(errorText(err, t, "passwordReset.failed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center bg-paper p-6">
      <section className="w-full max-w-md rounded-card border border-line bg-surface p-6 shadow-card sm:p-8">
        <Link href="/" className="mb-7 inline-flex items-center gap-2 font-display text-lg font-bold">
          <LogoMark size={36} decorative />
          <Wordmark />
        </Link>
        {done ? (
          <div className="text-center">
            <CheckCircle2 className="mx-auto text-ok" size={44} />
            <h1 className="mt-4 font-display text-2xl font-semibold">{t("passwordReset.doneTitle")}</h1>
            <p className="mt-2 text-sm text-muted">{t("passwordReset.doneBody")}</p>
            <Link href="/login" className="tap mt-6 inline-flex min-h-10 items-center justify-center rounded-control bg-accent px-5 py-2 text-sm font-semibold text-white">
              {t("ownerActivation.signIn")}
            </Link>
          </div>
        ) : (
          <form onSubmit={submit}>
            <KeyRound className="mb-4 text-accent" size={32} />
            <h1 className="font-display text-2xl font-semibold">{t("passwordReset.newTitle")}</h1>
            <p className="mt-2 text-sm text-muted">{t("passwordReset.newSubtitle")}</p>
            <div className="mt-6 space-y-4">
              <Field label={t("ownerActivation.password")} hint={t("users.passwordMin")}>
                <PasswordInput autoComplete="new-password" minLength={10} value={password} onChange={(e) => setPassword(e.target.value)} required className={INPUT_CLASS} />
              </Field>
              <Field label={t("ownerActivation.confirmPassword")}>
                <PasswordInput autoComplete="new-password" minLength={10} value={confirm} onChange={(e) => setConfirm(e.target.value)} required className={INPUT_CLASS} />
              </Field>
              {error && <p role="alert" className="rounded-control border border-danger/25 bg-danger/10 p-3 text-sm text-danger">{error}</p>}
              <Button type="submit" className="w-full" disabled={busy || password.length < 10 || confirm.length < 10}>
                {busy ? t("common.saving") : t("passwordReset.setPassword")}
              </Button>
              {!uid && <Link href="/forgot-password" className="block text-center text-sm text-muted hover:text-ink">{t("passwordReset.requestAgain")}</Link>}
            </div>
          </form>
        )}
      </section>
    </main>
  );
}
