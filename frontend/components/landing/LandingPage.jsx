"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  Boxes,
  Contact,
  Globe,
  Languages,
  LayoutDashboard,
  Menu,
  MoonStar,
  Package,
  RotateCcw,
  ShieldCheck,
  ShoppingCart,
  Sun,
  SunMoon,
  Truck,
  Users,
  X,
} from "lucide-react";

import { useAuth } from "../../app/providers/AuthProvider";
import { useI18n } from "../../app/providers/I18nProvider";

import { demoRequests } from "@/lib/api";
import { DEMO_URL, HAS_LIVE_DEMO } from "@/lib/demo";
import { MarketingFooter, MarketingHeader } from "@/components/marketing/Chrome";
import PlanCards from "@/components/marketing/PlanCards";

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

function Hero() {
  const { t } = useI18n();
  const { user } = useAuth();
  return (
    <section className="relative overflow-hidden">
      <div className="pointer-events-none absolute inset-0 -z-10 bg-gradient-to-b from-accent/10 to-transparent" />
      <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-24 lg:py-28">
        <div className="mx-auto max-w-3xl text-center">
          <span className="inline-flex items-center rounded-full border border-line bg-surface px-3 py-1 text-xs font-medium text-muted">
            {t("improvements.productBadge")}
          </span>
          <h1 className="mt-5 font-display text-3xl font-bold leading-tight tracking-tight sm:text-5xl">
            {t("improvements.productTitle")}
          </h1>
          <p className="mx-auto mt-5 max-w-2xl text-base text-muted sm:text-lg">
            {t("improvements.productSubtitle")}
          </p>
          <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <a
              href="/register"
              className="w-full rounded-control bg-accent px-6 py-3 text-center font-medium text-white hover:bg-accent-strong sm:w-auto"
            >
              {t("landing.heroCtaPrimary")}
            </a>
            <a
              href={DEMO_URL}
              target={HAS_LIVE_DEMO ? "_blank" : undefined}
              rel={HAS_LIVE_DEMO ? "noreferrer" : undefined}
              className="w-full rounded-control border border-line bg-surface px-6 py-3 text-center font-medium text-ink hover:border-accent sm:w-auto"
            >
              {t(HAS_LIVE_DEMO ? "landing.heroCtaDemo" : "landing.heroCtaTrial")}
            </a>
            <Link
              href={user ? "/dashboard" : "/login"}
              className="w-full rounded-control border border-line bg-surface px-6 py-3 text-center font-medium text-ink hover:border-accent sm:w-auto"
            >
              {user ? t("nav.dashboard") : t("landing.heroCtaSecondary")}
            </Link>
          </div>
          <p className="mt-6 text-sm text-muted">{t("improvements.productProof")}</p>
          <div className="mt-10 rounded-card border border-line bg-surface p-5 text-start shadow-card">
            <p className="text-xs text-muted">{t("improvements.previewLabel")}</p>
            <h2 className="mt-2 font-display text-xl font-semibold">{t("improvements.previewTitle")}</h2>
            <div className="mt-5 grid gap-3 sm:grid-cols-3">
              {[["previewSales","24,500"],["previewStock","8"],["previewDue","6,200"]].map(([key,value]) =>
                <div key={key} className="rounded-control bg-paper p-4"><div className="text-xs text-muted">{t(`improvements.${key}`)}</div><div className="tabular mt-2 text-2xl text-accent">{value}</div></div>)}
            </div>
            <p className="mt-5 font-medium text-accent">{t("improvements.previewAction")}</p>
            <p className="mt-2 text-sm text-muted">{t("improvements.previewHint")}</p>
          </div>
        </div>
      </div>
    </section>
  );
}

function PricingPreview() {
  const { t } = useI18n();
  return (
    <section id="pricing" className="border-t border-line bg-surface">
      <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-24">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="font-display text-2xl font-bold tracking-tight sm:text-3xl">{t("pricing.title")}</h2>
          <p className="mt-3 text-muted">{t("pricing.subtitle")}</p>
        </div>
        <div className="mt-10">
          <PlanCards compact />
        </div>
        <div className="mt-8 text-center">
          <Link href="/pricing" className="inline-flex items-center gap-2 rounded-control border border-line bg-paper px-5 py-3 font-medium text-ink hover:border-accent">
            {t("pricing.seeAll")}
          </Link>
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
  const [sent, setSent] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const requestId = useRef(null);
  async function onSubmit(e) {
    e.preventDefault();
    if (busy) return;
    const form = new FormData(e.currentTarget);
    requestId.current ||= crypto.randomUUID();
    setBusy(true); setError("");
    try {
      const res = await demoRequests.create({ request_uuid: requestId.current,
        name: form.get("name"), email: form.get("email"), message: form.get("message"), website: form.get("website") });
      setSent(res.data.reference);
    } catch (err) { setError(t(err?.response?.status === 503 ? "improvements.contactUnavailable" : "improvements.contactError")); }
    finally { setBusy(false); }
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
            {t("landing.contactSent")}<span className="mt-2 block text-xs">{t("improvements.contactReference", { id: sent })}</span>
          </p>
        ) : (
          <form onSubmit={onSubmit} className="mt-8 space-y-4">
            <div className="hidden" aria-hidden="true"><input name="website" tabIndex={-1} autoComplete="off" /></div>
            {error && <p role="alert" className="text-danger">{error}</p>}
            <div className="grid gap-4 sm:grid-cols-2">
              <input
                required name="name" maxLength={255} aria-label={t("landing.contactName")}
                placeholder={t("landing.contactName")}
                className="w-full rounded-control border border-line bg-paper px-3 py-3 outline-none focus:border-accent"
              />
              <input
                type="email" name="email" maxLength={254} aria-label={t("landing.contactEmail")}
                required
                placeholder={t("landing.contactEmail")}
                className="w-full rounded-control border border-line bg-paper px-3 py-3 outline-none focus:border-accent"
              />
            </div>
            <textarea
              rows={4} name="message" maxLength={4000} aria-label={t("landing.contactMessage")}
              placeholder={t("landing.contactMessage")}
              className="w-full rounded-control border border-line bg-paper px-3 py-3 outline-none focus:border-accent"
            />
            <button
              type="submit" disabled={busy}
              className="w-full rounded-control bg-accent py-3 font-medium text-white hover:bg-accent-strong"
            >
              {busy ? t("improvements.contactSending") : t("landing.contactSend")}
            </button>
          </form>
        )}
      </div>
    </section>
  );
}

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-paper text-ink">
      <MarketingHeader />
      <main>
        <Hero />
        <ValueProp />
        <Features />
        <Modules />
        <PricingPreview />
        <ContactCTA />
      </main>
      <MarketingFooter />
    </div>
  );
}
