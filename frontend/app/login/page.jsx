"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Languages } from "lucide-react";

import { useAuth } from "../providers/AuthProvider";
import { useI18n } from "../providers/I18nProvider";
import VezanoMark from "@/components/brand/VezanoMark";

export default function LoginPage() {
  const { user, loading, login } = useAuth();
  const { t, language, toggleLanguage } = useI18n();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [ownerContact, setOwnerContact] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!loading && user) router.replace("/dashboard");
  }, [loading, user, router]);

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await login(email, password);
      router.replace("/dashboard");
    } catch (err) {
      const data = err?.response?.data;
      if (data?.code === "store_mode_restricted") {
        setError(t("auth.storeModeRestricted"));
        setOwnerContact(data.owner_contact || "");
      } else {
        setError(t("auth.invalid"));
      }
      setSubmitting(false);
    }
  }

  return (
    <main className="grid min-h-screen lg:grid-cols-2">
      <section className="hidden flex-col justify-between bg-ink p-12 text-paper lg:flex">
        <Link href="/" className="flex items-center gap-2 font-display text-lg font-semibold tracking-tight">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-accent"><VezanoMark size={20} /></span>
          {t("common.appName")}
        </Link>
        <div>
          <h1 className="font-display text-4xl font-bold leading-tight">
            {t("auth.heroTitle")}
          </h1>
          <p className="mt-4 max-w-sm text-paper/70">{t("auth.heroSubtitle")}</p>
        </div>
        <div className="tabular text-sm text-paper/50">{t("auth.tagline")}</div>
      </section>

      {/* Sign-in */}
      <section className="relative flex items-center justify-center p-6">
        <button
          onClick={toggleLanguage}
          className="absolute end-4 top-4 flex items-center gap-1.5 rounded-control px-2.5 py-1.5 text-sm text-muted hover:bg-surface hover:text-ink"
        >
          <Languages size={16} />
          {language === "ar" ? "العربية" : "EN"}
        </button>
        <form onSubmit={onSubmit} className="w-full max-w-sm">
          <Link
            href="/"
            className="mb-6 inline-flex items-center gap-2 font-display text-lg font-bold tracking-tight lg:hidden"
          >
            <span className="grid h-8 w-8 place-items-center rounded-lg bg-accent text-white"><VezanoMark size={20} /></span>
            {t("common.appName")}
          </Link>
          <h2 className="font-display text-2xl font-semibold">{t("auth.signInHeading")}</h2>
          <p className="mt-1 text-sm text-muted">{t("auth.signInSubtitle")}</p>

          <label className="mt-6 block text-sm font-medium">{t("auth.emailLabel")}</label>
          <input
            type="email"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            className="mt-1 w-full rounded-control border border-line bg-surface px-3 py-2.5 outline-none focus:border-accent"
          />

          <label className="mt-4 block text-sm font-medium">{t("auth.passwordLabel")}</label>
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            className="mt-1 w-full rounded-control border border-line bg-surface px-3 py-2.5 outline-none focus:border-accent"
          />

          {error && (
            <div className="mt-3 rounded-control border border-warn/30 bg-warn/10 p-3 text-sm text-ink" role="alert">
              <p className="font-semibold">{error}</p>
              {ownerContact && <a className="mt-2 inline-block font-medium text-accent hover:underline" href={`mailto:${ownerContact}`}>{t("auth.contactOwner")}</a>}
            </div>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="mt-6 w-full rounded-control bg-accent py-3 font-medium text-white transition-colors hover:bg-accent-strong disabled:opacity-60"
          >
            {submitting ? t("auth.signingIn") : t("auth.signInHeading")}
          </button>
        </form>
      </section>
    </main>
  );
}
