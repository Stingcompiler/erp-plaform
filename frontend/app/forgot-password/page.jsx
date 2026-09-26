"use client";

import { useState } from "react";
import Link from "next/link";
import { MailCheck, KeyRound } from "lucide-react";

import LogoMark from "@/components/brand/LogoMark";
import Wordmark from "@/components/brand/Wordmark";
import { Button, Field, Input } from "@/components/ui/kit";
import { auth } from "@/lib/api";
import { useI18n } from "../providers/I18nProvider";

export default function ForgotPasswordPage() {
  const { t } = useI18n();
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  async function submit(event) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      const r = await auth.requestPasswordReset(email.trim());
      setResult(r.data);
    } catch (err) {
      setError(err?.response?.status === 429 ? t("passwordReset.tooMany") : t("passwordReset.failed"));
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
        {result ? (
          <div className="text-center">
            <MailCheck className="mx-auto text-ok" size={44} />
            <h1 className="mt-4 font-display text-2xl font-semibold">
              {result.email_enabled ? t("passwordReset.sentTitle") : t("passwordReset.noEmailTitle")}
            </h1>
            <p className="mt-2 text-sm text-muted">
              {result.email_enabled ? t("passwordReset.sentBody", { email }) : t("passwordReset.noEmailBody")}
            </p>
            <Link href="/login" className="tap mt-6 inline-flex min-h-10 items-center justify-center rounded-control bg-accent px-5 py-2 text-sm font-semibold text-white">
              {t("passwordReset.backToLogin")}
            </Link>
          </div>
        ) : (
          <form onSubmit={submit}>
            <KeyRound className="mb-4 text-accent" size={32} />
            <h1 className="font-display text-2xl font-semibold">{t("passwordReset.title")}</h1>
            <p className="mt-2 text-sm text-muted">{t("passwordReset.subtitle")}</p>
            <div className="mt-6 space-y-4">
              <Field label={t("auth.emailLabel")}>
                <Input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
              </Field>
              {error && <p role="alert" className="rounded-control border border-danger/25 bg-danger/10 p-3 text-sm text-danger">{error}</p>}
              <Button type="submit" className="w-full" disabled={busy || !email}>{busy ? t("passwordReset.sending") : t("passwordReset.send")}</Button>
              <Link href="/login" className="block text-center text-sm text-muted hover:text-ink">{t("passwordReset.backToLogin")}</Link>
            </div>
          </form>
        )}
      </section>
    </main>
  );
}
