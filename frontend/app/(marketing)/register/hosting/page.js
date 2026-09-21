"use client";

// "Cloud or your own server?" — the two delivery modes of the registration
// form explained side by side, with a way back to the form that keeps the
// visitor's choice.

import Link from "next/link";
import { ArrowLeft, ArrowRight, Check, Cloud, Server } from "lucide-react";

import { useI18n } from "@/app/providers/I18nProvider";
import { MarketingPage } from "@/components/marketing/Chrome";

const ICONS = { saas: Cloud, standalone: Server };

export default function HostingPage() {
  const { t, href, dir } = useI18n();
  const options = t("register.hosting.options");
  // "Back" points against the reading direction.
  const Back = dir === "rtl" ? ArrowRight : ArrowLeft;
  return (
    <MarketingPage>
      <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
        <Link href={href("/register")} className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink">
          <Back size={16} />
          {t("register.hosting.back")}
        </Link>
        <div className="mx-auto mt-6 max-w-2xl text-center">
          <h1 className="font-display text-3xl font-bold tracking-tight sm:text-4xl">{t("register.hosting.title")}</h1>
          <p className="mt-4 text-muted sm:text-lg">{t("register.hosting.subtitle")}</p>
        </div>
        <div className="mx-auto mt-10 grid max-w-5xl gap-6 md:grid-cols-2">
          {(Array.isArray(options) ? options : []).map((option) => {
            const Icon = ICONS[option.key] || Cloud;
            const standalone = option.key === "standalone";
            return (
              <article key={option.key} className="flex flex-col rounded-card border border-line bg-paper p-6 shadow-card sm:p-8">
                <div className="flex items-center gap-3">
                  <span className="grid h-11 w-11 place-items-center rounded-control bg-accent/10 text-accent"><Icon size={22} /></span>
                  <h2 className="font-display text-xl font-semibold">{option.title}</h2>
                </div>
                <p className="mt-3 text-muted">{option.tagline}</p>
                <ul className="mt-5 space-y-2.5 text-sm">
                  {option.points.map((line) => (
                    <li key={line} className="flex items-start gap-2">
                      <Check size={16} className="mt-0.5 shrink-0 text-accent" />
                      <span>{line}</span>
                    </li>
                  ))}
                </ul>
                <p className="mt-5 rounded-control bg-surface px-3 py-2 text-sm text-muted">{option.bestFor}</p>
                <Link
                  href={href(standalone ? "/register?mode=standalone" : "/register")}
                  className={`mt-6 rounded-control px-5 py-3 text-center font-medium ${
                    standalone ? "border border-line bg-surface text-ink hover:border-accent" : "bg-accent text-white hover:bg-accent-strong"
                  }`}
                >
                  {t(standalone ? "register.hosting.ctaStandalone" : "register.hosting.cta")}
                </Link>
              </article>
            );
          })}
        </div>
        <div className="mt-10 text-center">
          <Link href={href("/register")} className="inline-flex items-center gap-2 rounded-control border border-line bg-surface px-5 py-3 font-medium hover:border-accent">
            <Back size={16} />
            {t("register.hosting.back")}
          </Link>
        </div>
      </section>
    </MarketingPage>
  );
}
