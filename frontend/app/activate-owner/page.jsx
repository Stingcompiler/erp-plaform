"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { CheckCircle2, KeyRound } from "lucide-react";

import LogoMark from "@/components/brand/LogoMark";
import Wordmark from "@/components/brand/Wordmark";
import PasswordInput from "@/components/ui/PasswordInput";
import { Button, Field, Input, controlClass as INPUT_CLASS } from "@/components/ui/kit";
import { registration } from "@/lib/api";
import { useI18n } from "../providers/I18nProvider";
import { errorText } from "@/lib/errors";

export default function ActivateOwnerPage() {
  const { t } = useI18n();
  const [token, setToken] = useState("");
  const [kind, setKind] = useState("owner");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [activated, setActivated] = useState(false);

  // The token is read once and then scrubbed from the address bar so it does
  // not linger in history or get pasted along with the URL. Only touch state
  // when a token is actually present: this effect may run twice (StrictMode),
  // and the second run sees the already-scrubbed URL.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const invitationToken = params.get("token");
    if (!invitationToken) return;
    setToken(invitationToken);
    if (params.get("kind") === "platform") setKind("platform");
    window.history.replaceState({}, "", "/activate-owner/");
  }, []);

  async function activate(event) {
    event.preventDefault();
    setError("");
    if (!token) {
      setError(t("ownerActivation.missingToken"));
      return;
    }
    if (password !== confirmPassword) {
      setError(t("ownerActivation.mismatch"));
      return;
    }
    setSaving(true);
    try {
      await registration.activateOwner(token, password, kind);
      setActivated(true);
    } catch (requestError) {
      setError(errorText(requestError, t, "ownerActivation.failed"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center bg-paper p-6">
      <section className="w-full max-w-md rounded-card border border-line bg-surface p-6 shadow-card sm:p-8">
        <Link href="/" className="mb-7 inline-flex items-center gap-2 font-display text-lg font-bold">
          <LogoMark size={36} decorative />
          <Wordmark />
        </Link>
        {activated ? (
          <div className="text-center">
            <CheckCircle2 className="mx-auto text-ok" size={44} />
            <h1 className="mt-4 font-display text-2xl font-semibold">
              {t(kind === "platform" ? "ownerActivation.platformSuccess" : "ownerActivation.success")}
            </h1>
            <Link
              href="/login"
              className="tap mt-6 inline-flex min-h-10 items-center justify-center rounded-control bg-accent px-5 py-2 text-sm font-semibold text-white"
            >
              {t("ownerActivation.signIn")}
            </Link>
          </div>
        ) : (
          <form onSubmit={activate}>
            <KeyRound className="mb-4 text-accent" size={32} />
            <h1 className="font-display text-2xl font-semibold">
              {t(kind === "platform" ? "ownerActivation.platformTitle" : "ownerActivation.title")}
            </h1>
            <p className="mt-2 text-sm text-muted">
              {t(kind === "platform" ? "ownerActivation.platformSubtitle" : "ownerActivation.subtitle")}
            </p>
            <div className="mt-6 space-y-4">
              <Field label={t("ownerActivation.token")} hint={t("ownerActivation.tokenHint")}>
                <Input value={token} onChange={(event) => setToken(event.target.value)} required />
              </Field>
              <Field label={t("ownerActivation.password")} hint={t("users.passwordMin")}>
                <PasswordInput autoComplete="new-password" minLength={10} value={password} onChange={(event) => setPassword(event.target.value)} required className={INPUT_CLASS} />
              </Field>
              <Field label={t("ownerActivation.confirmPassword")}>
                <PasswordInput autoComplete="new-password" minLength={10} value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} required className={INPUT_CLASS} />
              </Field>
              {error && (
                <p role="alert" className="rounded-control border border-danger/25 bg-danger/10 p-3 text-sm text-danger">
                  {error}
                </p>
              )}
              <Button type="submit" className="w-full" disabled={saving || password.length < 10 || confirmPassword.length < 10}>
                {saving ? t("ownerActivation.activating") : t("ownerActivation.activate")}
              </Button>
            </div>
          </form>
        )}
      </section>
    </main>
  );
}
