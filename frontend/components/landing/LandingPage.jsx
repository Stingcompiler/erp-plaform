"use client";

import { useState } from "react";
import Link from "next/link";
import {
  Boxes,
  Contact,
  Globe,
  Languages,
  LayoutDashboard,
  MoonStar,
  Package,
  RotateCcw,
  ShieldCheck,
  ShoppingCart,
  Sun,
  SunMoon,
  Truck,
  Users,
} from "lucide-react";

import { useAuth } from "../../app/providers/AuthProvider";
import { useI18n } from "../../app/providers/I18nProvider";

const FEATURES = [
  { icon: Package, titleKey: "landing.feature1Title", bodyKey: "landing.feature1Body" },
  { icon: ShoppingCart, titleKey: "landing.feature2Title", bodyKey: "landing.feature2Body" },
  { icon: Truck, titleKey: "landing.feature3Title", bodyKey: "landing.feature3Body" },
  { icon: Contact, titleKey: "landing.feature4Title", bodyKey: "landing.feature4Body" },
  { icon: Languages, titleKey: "landing.feature5Title", bodyKey: "landing.feature5Body" },
  { icon: ShieldCheck, titleKey: "landing.feature6Title", bodyKey: "landing.feature6Body" },
];

const MODULES = [
  { icon: LayoutDashboard, key: "nav.dashboard" },
  { icon: Package, key: "nav.inventory" },
  { icon: ShoppingCart, key: "nav.sales" },
  { icon: Truck, key: "nav.purchasing" },
  { icon: RotateCcw, key: "nav.returns" },
  { icon: Contact, key: "nav.crm" },
  { icon: Boxes, key: "nav.reports" },
  { icon: Globe, key: "nav.website" },
  { icon: Users, key: "nav.users" },
];

function ThemeToggle() {
  const { t, theme, cycleTheme } = useI18n();
  const Icon = theme === "dark" ? MoonStar : theme === "light" ? Sun : SunMoon;
  return (
    <button
      onClick={cycleTheme}
      aria-label={t("shell.theme")}
      className="grid h-10 w-10 place-items-center rounded-control text-muted hover:bg-surface hover:text-ink"
    >
      <Icon size={18} />
    </button>
  );
}

function LangToggle() {
  const { language, toggleLanguage, t } = useI18n();
  return (
    <button
      onClick={toggleLanguage}
      title={t("shell.switchLanguage")}
      className="flex h-10 items-center gap-1.5 rounded-control px-2.5 text-sm font-medium text-muted hover:bg-surface hover:text-ink"
    >
      <Languages size={16} />
      {language === "ar" ? "العربية" : "EN"}
    </button>
  );
}

function Header() {
  const { t } = useI18n();
  const { user } = useAuth();
  return (
    <header className="sticky top-0 z-30 border-b border-line/70 bg-paper/80 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-3 px-4 sm:px-6">
        <Link href="/" className="font-display text-lg font-bold tracking-tight">
          ERP
        </Link>
        <nav className="hidden items-center gap-6 text-sm text-muted md:flex">
          <a href="#features" className="hover:text-ink">{t("landing.navFeatures")}</a>
          <a href="#modules" className="hover:text-ink">{t("landing.navModules")}</a>
          <a href="#contact" className="hover:text-ink">{t("landing.navContact")}</a>
        </nav>
        <div className="flex items-center gap-1">
          <LangToggle />
          <ThemeToggle />
          <Link
            href={user ? "/dashboard" : "/login"}
            className="ms-1 rounded-control bg-accent px-3.5 py-2 text-sm font-medium text-white hover:bg-accent-strong"
          >
            {user ? t("nav.dashboard") : t("common.signIn")}
          </Link>
        </div>
      </div>
    </header>
  );
}

function Hero() {
  const { t } = useI18n();
  const { user } = useAuth();
  return (
    <section className="relative overflow-hidden">
      <div className="pointer-events-none absolute inset-0 -z-10 bg-gradient-to-b from-accent/10 to-transparent" />
      <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-24 lg:py-28">
        <div className="mx-auto max-w-3xl text-center">
          <span className="inline-flex items-center rounded-full border border-line bg-surface px-3 py-1 text-xs font-medium text-muted">
            {t("landing.heroBadge")}
          </span>
          <h1 className="mt-5 font-display text-3xl font-bold leading-tight tracking-tight sm:text-5xl">
            {t("landing.heroTitle")}
          </h1>
          <p className="mx-auto mt-5 max-w-2xl text-base text-muted sm:text-lg">
            {t("landing.heroSubtitle")}
          </p>
          <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <a
              href="#contact"
              className="w-full rounded-control bg-accent px-6 py-3 text-center font-medium text-white hover:bg-accent-strong sm:w-auto"
            >
              {t("landing.heroCtaPrimary")}
            </a>
            <Link
              href={user ? "/dashboard" : "/login"}
              className="w-full rounded-control border border-line bg-surface px-6 py-3 text-center font-medium text-ink hover:border-accent sm:w-auto"
            >
              {user ? t("nav.dashboard") : t("landing.heroCtaSecondary")}
            </Link>
          </div>
          <p className="mt-6 text-sm text-muted">{t("landing.trustedBy")}</p>
        </div>
      </div>
    </section>
  );
}

function ValueProp() {
  const { t } = useI18n();
  return (
    <section className="border-y border-line bg-surface">
      <div className="mx-auto max-w-4xl px-4 py-14 text-center sm:px-6 sm:py-20">
        <h2 className="font-display text-2xl font-bold tracking-tight sm:text-3xl">
          {t("landing.valueTitle")}
        </h2>
        <p className="mx-auto mt-4 max-w-2xl text-muted">{t("landing.valueSubtitle")}</p>
      </div>
    </section>
  );
}

function Features() {
  const { t } = useI18n();
  return (
    <section id="features" className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-24">
      <div className="mx-auto max-w-2xl text-center">
        <h2 className="font-display text-2xl font-bold tracking-tight sm:text-3xl">
          {t("landing.modulesTitle")}
        </h2>
        <p className="mt-3 text-muted">{t("landing.modulesSubtitle")}</p>
      </div>
      <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {FEATURES.map(({ icon: Icon, titleKey, bodyKey }) => (
          <div
            key={titleKey}
            className="rounded-card border border-line bg-surface p-6 shadow-card"
          >
            <div className="grid h-11 w-11 place-items-center rounded-control bg-accent/10 text-accent">
              <Icon size={22} />
            </div>
            <h3 className="mt-4 font-display text-lg font-semibold">{t(titleKey)}</h3>
            <p className="mt-2 text-sm text-muted">{t(bodyKey)}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function Modules() {
  const { t } = useI18n();
  return (
    <section id="modules" className="border-t border-line bg-surface">
      <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-20">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {MODULES.map(({ icon: Icon, key }) => (
            <div
              key={key}
              className="flex items-center gap-3 rounded-control border border-line bg-paper px-4 py-3"
            >
              <Icon size={18} className="shrink-0 text-accent" />
              <span className="text-sm font-medium">{t(key)}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function ContactCTA() {
  const { t } = useI18n();
  const [sent, setSent] = useState(false);

  function onSubmit(e) {
    e.preventDefault();
    // No marketing backend endpoint yet — confirm receipt client-side. Wire to
    // a real lead-capture endpoint when one exists.
    setSent(true);
  }

  return (
    <section id="contact" className="mx-auto max-w-3xl px-4 py-16 sm:px-6 sm:py-24">
      <div className="rounded-card border border-line bg-surface p-6 shadow-card sm:p-10">
        <div className="text-center">
          <h2 className="font-display text-2xl font-bold tracking-tight sm:text-3xl">
            {t("landing.ctaTitle")}
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-muted">{t("landing.ctaSubtitle")}</p>
        </div>
        {sent ? (
          <p className="mt-8 rounded-control bg-ok/10 px-4 py-6 text-center font-medium text-ok">
            {t("landing.contactSent")}
          </p>
        ) : (
          <form onSubmit={onSubmit} className="mt-8 space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <input
                required
                placeholder={t("landing.contactName")}
                className="w-full rounded-control border border-line bg-paper px-3 py-3 outline-none focus:border-accent"
              />
              <input
                type="email"
                required
                placeholder={t("landing.contactEmail")}
                className="w-full rounded-control border border-line bg-paper px-3 py-3 outline-none focus:border-accent"
              />
            </div>
            <textarea
              rows={4}
              placeholder={t("landing.contactMessage")}
              className="w-full rounded-control border border-line bg-paper px-3 py-3 outline-none focus:border-accent"
            />
            <button
              type="submit"
              className="w-full rounded-control bg-accent py-3 font-medium text-white hover:bg-accent-strong"
            >
              {t("landing.contactSend")}
            </button>
          </form>
        )}
      </div>
    </section>
  );
}

function Footer() {
  const { t } = useI18n();
  const year = new Date().getFullYear();
  return (
    <footer className="border-t border-line bg-ink text-paper">
      <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6">
        <div className="flex flex-col gap-8 sm:flex-row sm:justify-between">
          <div className="max-w-xs">
            <div className="font-display text-lg font-bold tracking-tight">ERP</div>
            <p className="mt-2 text-sm text-paper/60">{t("landing.footerTagline")}</p>
          </div>
          <div className="flex gap-12">
            <div>
              <div className="text-sm font-semibold text-paper/90">
                {t("landing.footerProduct")}
              </div>
              <ul className="mt-3 space-y-2 text-sm text-paper/60">
                <li><a href="#features" className="hover:text-paper">{t("landing.navFeatures")}</a></li>
                <li><a href="#modules" className="hover:text-paper">{t("landing.navModules")}</a></li>
                <li><Link href="/login" className="hover:text-paper">{t("common.signIn")}</Link></li>
              </ul>
            </div>
            <div>
              <div className="text-sm font-semibold text-paper/90">
                {t("landing.footerCompany")}
              </div>
              <ul className="mt-3 space-y-2 text-sm text-paper/60">
                <li><a href="#contact" className="hover:text-paper">{t("landing.navContact")}</a></li>
              </ul>
            </div>
          </div>
        </div>
        <div className="mt-10 border-t border-white/10 pt-6 text-sm text-paper/50">
          © {year} ERP. {t("landing.footerRights")}
        </div>
      </div>
    </footer>
  );
}

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-paper text-ink">
      <Header />
      <main>
        <Hero />
        <ValueProp />
        <Features />
        <Modules />
        <ContactCTA />
      </main>
      <Footer />
    </div>
  );
}
