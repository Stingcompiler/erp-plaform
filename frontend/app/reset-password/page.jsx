"use client";

// Reset links were retired on 2026-10-01 (accounts/password_reset.py now
// emails a 6-digit code; an old link's uid/token is refused with
// `link_flow_retired`). Anyone arriving from an old email is told so and
// taken to /forgot-password to ask for a code.

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { MailCheck } from "lucide-react";

import LogoMark from "@/components/brand/LogoMark";
import Wordmark from "@/components/brand/Wordmark";
import { useI18n } from "../providers/I18nProvider";

const REDIRECT_AFTER = 8;

export default function ResetPasswordPage() {
  const { t } = useI18n();
  const router = useRouter();
  const [seconds, setSeconds] = useState(REDIRECT_AFTER);

  useEffect(() => {
    // Old links carried a token: keep it out of history.
    if (window.location.search) window.history.replaceState({}, "", "/reset-password/");
    const timer = setInterval(() => setSeconds((left) => Math.max(0, left - 1)), 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (seconds === 0) router.replace("/forgot-password/");
  }, [seconds, router]);

  return (
    <main className="grid min-h-screen place-items-center bg-paper px-4 py-8 sm:p-6">
      <div className="w-full max-w-md">
        <Link href="/" className="mb-6 inline-flex items-center gap-2 font-display text-lg font-bold">
          <LogoMark size={36} decorative />
          <Wordmark />
        </Link>
        <section className="enter-rise rounded-card border border-line bg-surface p-6 text-center shadow-card sm:p-8">
          <span className="mx-auto grid h-14 w-14 place-items-center rounded-full bg-accent/10 text-accent">
            <MailCheck size={28} aria-hidden="true" />
          </span>
          <h1 className="mt-4 font-display text-2xl font-semibold">{t("passwordReset.retiredTitle")}</h1>
          <p className="mt-2 text-sm text-muted">{t("passwordReset.retiredBody")}</p>
          <Link
            href="/forgot-password/"
            className="tap mt-6 inline-flex min-h-11 w-full items-center justify-center rounded-control bg-accent px-5 py-2 text-sm font-semibold text-white hover:bg-accent-strong"
          >
            {t("passwordReset.requestCode")}
          </Link>
          <p className="mt-3 text-xs text-muted" aria-live="polite">{t("passwordReset.retiredRedirect", { seconds })}</p>
          <Link href="/login" className="mt-4 block text-sm text-muted hover:text-ink">{t("passwordReset.backToLogin")}</Link>
        </section>
      </div>
    </main>
  );
}
