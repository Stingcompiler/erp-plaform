"use client";

// Public landing page for the hosted product. Every screenshot under
// /marketing is a real capture of the demo company (Arabic, light and dark),
// so the copy next to it describes what the visitor is actually looking at.

import { useRef, useState } from "react";
import Link from "next/link";
import { motion, useReducedMotion } from "framer-motion";
import {
  Boxes,
  Briefcase,
  Check,
  Contact,
  Globe,
  LayoutDashboard,
  Package,
  RotateCcw,
  ShoppingCart,
  Truck,
  Users,
  Wallet,
} from "lucide-react";

import { useAuth } from "../../app/providers/AuthProvider";
import { useI18n } from "../../app/providers/I18nProvider";

import { demoRequests } from "@/lib/api";
import { MarketingFooter, MarketingHeader } from "@/components/marketing/Chrome";
import PlanCards from "@/components/marketing/PlanCards";

const MODULES = [
  { icon: LayoutDashboard, key: "nav.dashboard" },
  { icon: Package, key: "nav.inventory" },
  { icon: ShoppingCart, key: "nav.sales" },
  { icon: Truck, key: "nav.purchasing" },
  { icon: RotateCcw, key: "nav.returns" },
  { icon: Contact, key: "nav.crm" },
  { icon: Wallet, key: "nav.finance" },
  { icon: Briefcase, key: "nav.hr" },
  { icon: Boxes, key: "nav.reports" },
  { icon: Globe, key: "nav.website" },
  { icon: Users, key: "nav.users" },
];

const STORY_SHOTS = [
  { light: "/marketing/pos.png", dark: "/marketing/pos-dark.png" },
  { light: "/marketing/inventory.png", dark: "/marketing/inventory.png" },
  { light: "/marketing/debts.png", dark: "/marketing/debts.png" },
];

// A screenshot inside a browser-window frame. Both themes are rendered and
// CSS picks one, so the picture follows the visitor's theme without JS.
function Shot({ light, dark, alt, priority = false, className = "" }) {
  const shared = "block w-full";
  return (
    <figure className={`overflow-hidden rounded-card border border-line bg-surface shadow-card ${className}`}>
      <div className="flex items-center gap-1.5 border-b border-line bg-paper px-3 py-2">
        <span className="h-2.5 w-2.5 rounded-full bg-danger/60" />
        <span className="h-2.5 w-2.5 rounded-full bg-warn/60" />
        <span className="h-2.5 w-2.5 rounded-full bg-ok/60" />
      </div>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={light} alt={alt} className={`${shared} ${dark !== light ? "dark:hidden" : ""}`} loading={priority ? "eager" : "lazy"} decoding="async" />
      {dark !== light && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={dark} alt="" aria-hidden="true" className={`${shared} hidden dark:block`} loading="lazy" decoding="async" />
      )}
    </figure>
  );
}

// Above the fold (`immediate`) animates on mount; everything else waits until
// it scrolls into view. Reduced-motion users get the final state at once.
function Reveal({ children, delay = 0, className = "", immediate = false }) {
  const reduce = useReducedMotion();
  const visible = { opacity: 1, y: 0 };
  return (
    <motion.div
      className={className}
      initial={reduce ? false : { opacity: 0, y: 18 }}
      animate={immediate ? visible : undefined}
      whileInView={immediate ? undefined : visible}
      viewport={{ once: true, margin: "-80px" }}
      transition={{ duration: 0.5, delay, ease: "easeOut" }}
    >
      {children}
    </motion.div>
  );
}

function Hero() {
  const { t } = useI18n();
  const { user } = useAuth();
  return (
    <section className="relative overflow-hidden">
      <div className="pointer-events-none absolute inset-0 -z-10 bg-gradient-to-b from-accent/10 via-transparent to-transparent" />
      <div className="pointer-events-none absolute start-1/2 top-24 -z-10 h-[480px] w-[900px] -translate-x-1/2 rounded-full bg-accent/10 blur-3xl" />
      <div className="mx-auto max-w-6xl px-4 pb-10 pt-14 sm:px-6 sm:pt-20">
        <div className="mx-auto max-w-3xl text-center">
          <Reveal immediate>
            <span className="inline-flex items-center rounded-full border border-line bg-surface px-3 py-1 text-xs font-medium text-muted">
              {t("home.heroBadge")}
            </span>
          </Reveal>
          <Reveal immediate delay={0.05}>
            <h1 className="mt-5 font-display text-4xl font-bold leading-[1.15] tracking-tight sm:text-6xl">
              {t("home.heroTitle")}
            </h1>
          </Reveal>
          <Reveal immediate delay={0.1}>
            <p className="mx-auto mt-5 max-w-2xl text-base text-muted sm:text-lg">{t("home.heroSubtitle")}</p>
          </Reveal>
          <Reveal immediate delay={0.15}>
            <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <Link href="/register" className="w-full rounded-control bg-accent px-6 py-3 text-center font-medium text-white shadow-card hover:bg-accent-strong sm:w-auto">
                {t("home.heroPrimary")}
              </Link>
              <Link href="/pricing" className="w-full rounded-control border border-line bg-surface px-6 py-3 text-center font-medium text-ink hover:border-accent sm:w-auto">
                {t("home.heroSecondary")}
              </Link>
              {user && (
                <Link href="/dashboard" className="w-full rounded-control px-6 py-3 text-center font-medium text-accent hover:underline sm:w-auto">
                  {t("nav.dashboard")}
                </Link>
              )}
            </div>
            <p className="mt-4 text-sm text-muted">{t("home.heroNote")}</p>
          </Reveal>
        </div>
        <Reveal immediate delay={0.2} className="mx-auto mt-12 max-w-5xl">
          <Shot light="/marketing/dashboard.png" dark="/marketing/dashboard-dark.png" alt={t("home.heroCaption")} priority />
          <p className="mt-3 text-center text-xs text-muted">{t("home.heroCaption")}</p>
        </Reveal>
      </div>
    </section>
  );
}

function TrustStrip() {
  const { t } = useI18n();
  const items = t("home.trust");
  if (!Array.isArray(items)) return null;
  return (
    <section className="border-y border-line bg-surface">
      <div className="mx-auto grid max-w-6xl gap-3 px-4 py-6 sm:grid-cols-2 sm:px-6 lg:grid-cols-4">
        {items.map((item) => (
          <div key={item} className="flex items-center justify-center gap-2 text-sm font-medium text-ink">
            <Check size={16} className="shrink-0 text-accent" />
            {item}
          </div>
        ))}
      </div>
    </section>
  );
}

function Stories() {
  const { t } = useI18n();
  const stories = t("home.stories");
  if (!Array.isArray(stories)) return null;
  return (
    <section id="features" className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-24">
      <h2 className="text-center font-display text-2xl font-bold tracking-tight sm:text-3xl">{t("home.storiesTitle")}</h2>
      <div className="mt-14 space-y-20">
        {stories.map((story, index) => {
          const shot = STORY_SHOTS[index] || STORY_SHOTS[0];
          const flip = index % 2 === 1;
          return (
            <Reveal key={story.title}>
              <div className={`grid items-center gap-8 lg:grid-cols-2 lg:gap-14 ${flip ? "lg:[&>*:first-child]:order-2" : ""}`}>
                <div>
                  <p className="text-sm font-semibold uppercase tracking-wide text-accent">{story.eyebrow}</p>
                  <h3 className="mt-2 font-display text-2xl font-bold tracking-tight sm:text-3xl">{story.title}</h3>
                  <p className="mt-4 text-muted sm:text-lg">{story.body}</p>
                  <ul className="mt-6 space-y-2.5">
                    {story.bullets.map((line) => (
                      <li key={line} className="flex items-start gap-2 text-sm sm:text-base">
                        <Check size={18} className="mt-0.5 shrink-0 text-accent" />
                        <span>{line}</span>
                      </li>
                    ))}
                  </ul>
                </div>
                <Shot light={shot.light} dark={shot.dark} alt={story.title} />
              </div>
            </Reveal>
          );
        })}
      </div>
    </section>
  );
}

function Modules() {
  const { t } = useI18n();
  return (
    <section id="modules" className="border-t border-line bg-surface">
      <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-24">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="font-display text-2xl font-bold tracking-tight sm:text-3xl">{t("landing.modulesTitle")}</h2>
          <p className="mt-3 text-muted">{t("landing.modulesSubtitle")}</p>
        </div>
        <div className="mt-10 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {MODULES.map(({ icon: Icon, key }, index) => (
            <Reveal key={key} delay={index * 0.03}>
              <div className="flex items-center gap-3 rounded-card border border-line bg-paper px-4 py-3.5 shadow-card">
                <span className="grid h-9 w-9 shrink-0 place-items-center rounded-control bg-accent/10 text-accent"><Icon size={18} /></span>
                <span className="text-sm font-medium">{t(key)}</span>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

function HowItWorks() {
  const { t } = useI18n();
  const steps = t("home.how");
  if (!Array.isArray(steps)) return null;
  return (
    <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-24">
      <h2 className="text-center font-display text-2xl font-bold tracking-tight sm:text-3xl">{t("home.howTitle")}</h2>
      <div className="mt-10 grid gap-5 md:grid-cols-3">
        {steps.map(([title, body], index) => (
          <Reveal key={title} delay={index * 0.08}>
            <div className="h-full rounded-card border border-line bg-paper p-6 shadow-card">
              <span className="grid h-9 w-9 place-items-center rounded-full bg-accent font-display text-sm font-bold text-white">{index + 1}</span>
              <h3 className="mt-4 font-display text-lg font-semibold">{title}</h3>
              <p className="mt-2 text-sm text-muted">{body}</p>
            </div>
          </Reveal>
        ))}
      </div>
    </section>
  );
}

function Faq() {
  const { t } = useI18n();
  const items = t("home.faq");
  if (!Array.isArray(items)) return null;
  return (
    <section className="border-t border-line bg-surface">
      <div className="mx-auto max-w-3xl px-4 py-16 sm:px-6 sm:py-24">
        <h2 className="text-center font-display text-2xl font-bold tracking-tight sm:text-3xl">{t("home.faqTitle")}</h2>
        <div className="mt-8 space-y-3">
          {items.map(([question, answer]) => (
            <details key={question} className="group rounded-card border border-line bg-paper p-5">
              <summary className="cursor-pointer list-none font-medium marker:content-none">{question}</summary>
              <p className="mt-3 text-sm text-muted">{answer}</p>
            </details>
          ))}
        </div>
      </div>
    </section>
  );
}

function FinalCta() {
  const { t } = useI18n();
  return (
    <section className="mx-auto max-w-6xl px-4 pb-4 pt-16 sm:px-6">
      <div className="relative overflow-hidden rounded-card bg-ink px-6 py-12 text-center text-paper shadow-card sm:px-12 sm:py-16">
        <div className="pointer-events-none absolute -end-24 -top-24 h-72 w-72 rounded-full bg-accent/30 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-24 -start-24 h-72 w-72 rounded-full bg-accent/20 blur-3xl" />
        <h2 className="relative font-display text-2xl font-bold tracking-tight sm:text-4xl">{t("home.finalTitle")}</h2>
        <p className="relative mx-auto mt-3 max-w-xl text-paper/70">{t("home.finalBody")}</p>
        <div className="relative mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <Link href="/register" className="w-full rounded-control bg-accent px-6 py-3 font-medium text-white hover:bg-accent-strong sm:w-auto">{t("home.finalPrimary")}</Link>
          <a href="#contact" className="w-full rounded-control border border-white/20 px-6 py-3 font-medium text-paper hover:bg-white/10 sm:w-auto">{t("home.finalSecondary")}</a>
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
        <TrustStrip />
        <Stories />
        <Modules />
        <HowItWorks />
        <PricingPreview />
        <Faq />
        <FinalCta />
        <ContactCTA />
      </main>
      <MarketingFooter />
    </div>
  );
}
