"use client";

// Public landing page for the hosted product. Every screenshot under
// /marketing is a real capture of the demo company (Arabic, light and dark),
// so the copy next to it describes what the visitor is actually looking at.

import { useRef, useState } from "react";
import Link from "next/link";
import { motion, useReducedMotion } from "framer-motion";
import {
  ArrowRight,
  Banknote,
  Briefcase,
  Building2,
  ChartColumn,
  Check,
  Contact,
  DatabaseBackup,
  Languages,
  LifeBuoy,
  Mail,
  MessageCircle,
  Package,
  ShieldCheck,
  ShoppingCart,
  Smartphone,
  Truck,
  Users,
  Wallet,
  WifiOff,
} from "lucide-react";

import { useI18n } from "../../app/providers/I18nProvider";
import Showcase from "@/components/landing/Showcase";
import InstallCard from "@/components/sync/InstallCard";

import { demoRequests } from "@/lib/api";
import { MarketingFooter, MarketingHeader } from "@/components/marketing/Chrome";
import { DirectWhatsAppLink, SiteContactProvider, WhatsAppFloat, useSiteContact } from "@/components/marketing/SiteContact";
import PlanCards from "@/components/marketing/PlanCards";
import Shot from "@/components/marketing/Shot";

// Icons for the module cards (home.modules[].key); the copy and the /product
// anchor each card links to live in lib/marketingI18n.js.
const MODULE_ICONS = {
  sales: ShoppingCart,
  inventory: Package,
  purchasing: Truck,
  crm: Contact,
  hr: Briefcase,
  finance: Wallet,
  reports: ChartColumn,
  branches: Building2,
};

const SUDAN_ICONS = [WifiOff, Smartphone, Languages, Banknote];

const STORY_SHOTS = [
  { light: "/marketing/pos.png", dark: "/marketing/pos-dark.png" },
  { light: "/marketing/inventory.png", dark: "/marketing/inventory.png" },
  { light: "/marketing/debts.png", dark: "/marketing/debts.png" },
];

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
  const { t, href } = useI18n();
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
            <h1 className="mt-5 font-display text-3xl font-bold leading-[1.2] tracking-tight sm:text-5xl">
              {t("home.heroTitle")}
            </h1>
          </Reveal>
          <Reveal immediate delay={0.1}>
            <p className="mx-auto mt-5 max-w-2xl text-base text-muted sm:text-lg">{t("home.heroSubtitle")}</p>
            <p className="mx-auto mt-4 flex max-w-2xl items-start justify-center gap-2 text-sm text-ink/80">
              <WifiOff size={16} aria-hidden="true" className="mt-0.5 shrink-0 text-accent" />
              <span>{t("home.heroOffline")}</span>
            </p>
          </Reveal>
          <Reveal immediate delay={0.15}>
            <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <Link href={href("/register")} className="w-full rounded-control bg-accent px-6 py-3 text-center font-medium text-white shadow-card hover:bg-accent-strong sm:w-auto">
                {t("home.heroPrimary")}
              </Link>
              <Link href={href("/pricing")} className="w-full rounded-control border border-line bg-surface px-6 py-3 text-center font-medium text-ink hover:border-accent sm:w-auto">
                {t("home.heroSecondary")}
              </Link>
            </div>
            <p className="mt-4 text-sm text-muted">{t("home.heroNote")}</p>
            <InstallCard className="mx-auto mt-6 max-w-md text-start" />
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
    <section id="features" className="mx-auto max-w-6xl border-t border-line px-4 py-16 sm:px-6 sm:py-24">
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

// Every department in one system: one card per module, each linking to its
// section of /product. Only what the code does (see the copy's comment).
function Modules() {
  const { t, href } = useI18n();
  const modules = t("home.modules");
  if (!Array.isArray(modules)) return null;
  return (
    <section id="modules" className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-24">
      <div className="mx-auto max-w-2xl text-center">
        <h2 className="font-display text-2xl font-bold tracking-tight sm:text-3xl">{t("home.modulesTitle")}</h2>
        <p className="mt-3 text-muted">{t("home.modulesSubtitle")}</p>
      </div>
      <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {modules.map((module, index) => {
          const Icon = MODULE_ICONS[module.key] || Package;
          return (
            <Reveal key={module.key} delay={index * 0.03} className="h-full">
              <Link
                href={href(`/product#${module.anchor}`)}
                className="group flex h-full flex-col rounded-card border border-line bg-surface p-5 shadow-card transition-colors hover:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
              >
                <span className="grid h-10 w-10 place-items-center rounded-control bg-accent/10 text-accent"><Icon size={20} aria-hidden="true" /></span>
                <h3 className="mt-4 font-display text-lg font-semibold">{module.title}</h3>
                <p className="mt-2 flex-1 text-sm text-muted">{module.body}</p>
                <span className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-accent">
                  {t("home.modulesMore")}
                  <ArrowRight size={15} aria-hidden="true" className="transition-transform group-hover:translate-x-0.5 rtl:rotate-180 rtl:group-hover:-translate-x-0.5" />
                </span>
              </Link>
            </Reveal>
          );
        })}
      </div>
    </section>
  );
}

// For companies with several branches and layered roles: branch scoping,
// the fixed role set (core.rbac / seed_roles) and the approval points.
function MultiBranch() {
  const { t } = useI18n();
  const roles = t("home.multiRoles");
  const approvals = t("home.multiApprovals");
  const card = "h-full rounded-card border border-line bg-paper p-6 shadow-card";
  const heading = "flex items-center gap-2 font-display text-lg font-semibold";
  return (
    <section id="branches" className="border-y border-line bg-surface">
      <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-24">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="font-display text-2xl font-bold tracking-tight sm:text-3xl">{t("home.multiTitle")}</h2>
          <p className="mt-3 text-muted">{t("home.multiSubtitle")}</p>
        </div>
        <div className="mt-10 grid gap-5 lg:grid-cols-3">
          <Reveal className="h-full">
            <div className={card}>
              <h3 className={heading}><Building2 size={20} aria-hidden="true" className="shrink-0 text-accent" />{t("home.multiBranchTitle")}</h3>
              <p className="mt-3 text-sm text-muted">{t("home.multiBranchBody")}</p>
            </div>
          </Reveal>
          <Reveal delay={0.05} className="h-full">
            <div className={card}>
              <h3 className={heading}><Users size={20} aria-hidden="true" className="shrink-0 text-accent" />{t("home.multiRolesTitle")}</h3>
              {Array.isArray(roles) && (
                <ul className="mt-4 flex flex-wrap gap-2">
                  {roles.map((role) => (
                    <li key={role} className="rounded-full border border-line bg-surface px-3 py-1 text-xs font-medium text-ink">{role}</li>
                  ))}
                </ul>
              )}
            </div>
          </Reveal>
          <Reveal delay={0.1} className="h-full">
            <div className={card}>
              <h3 className={heading}><ShieldCheck size={20} aria-hidden="true" className="shrink-0 text-accent" />{t("home.multiApprovalsTitle")}</h3>
              {Array.isArray(approvals) && (
                <ul className="mt-4 space-y-2.5 text-sm">
                  {approvals.map((line) => (
                    <li key={line} className="flex items-start gap-2">
                      <Check size={16} aria-hidden="true" className="mt-0.5 shrink-0 text-accent" /><span>{line}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  );
}

function SudanFit() {
  const { t } = useI18n();
  const items = t("home.sudan");
  if (!Array.isArray(items)) return null;
  return (
    <section id="sudan" className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-24">
      <h2 className="text-center font-display text-2xl font-bold tracking-tight sm:text-3xl">{t("home.sudanTitle")}</h2>
      <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {items.map(([title, body], index) => {
          const Icon = SUDAN_ICONS[index] || Check;
          return (
            <Reveal key={title} delay={index * 0.05} className="h-full">
              <div className="h-full rounded-card border border-line bg-paper p-5 shadow-card">
                <span className="grid h-9 w-9 place-items-center rounded-control bg-accent/10 text-accent"><Icon size={18} aria-hidden="true" /></span>
                <h3 className="mt-3 font-display font-semibold">{title}</h3>
                <p className="mt-2 text-sm text-muted">{body}</p>
              </div>
            </Reveal>
          );
        })}
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

// What a visitor can check before trusting us with the shop: what the
// nightly backup holds and how it comes back, and how to reach a person.
// Only what the product does (ops.snapshots / Settings → Backups); no
// response-time promise.
function TrustSupport() {
  const { t } = useI18n();
  const { email, whatsapp, whatsappHref } = useSiteContact();
  const points = t("home.backupPoints");
  const linkClass = "inline-flex items-center gap-2 rounded-control border border-line bg-paper px-4 py-2 text-sm font-medium text-ink hover:border-accent";
  return (
    <section id="trust" className="mx-auto max-w-6xl px-4 pb-16 sm:px-6 sm:pb-24">
      <div className="grid gap-5 md:grid-cols-2">
        <div className="rounded-card border border-line bg-surface p-6 shadow-card">
          <h2 className="flex items-center gap-2 font-display text-xl font-bold">
            <DatabaseBackup size={20} aria-hidden="true" className="text-accent" />{t("home.backupTitle")}
          </h2>
          {Array.isArray(points) && (
            <ul className="mt-4 space-y-2.5 text-sm">
              {points.map((line) => (
                <li key={line} className="flex items-start gap-2">
                  <Check size={16} aria-hidden="true" className="mt-0.5 shrink-0 text-accent" /><span>{line}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="rounded-card border border-line bg-surface p-6 shadow-card">
          <h2 className="flex items-center gap-2 font-display text-xl font-bold">
            <LifeBuoy size={20} aria-hidden="true" className="text-accent" />{t("home.supportTitle")}
          </h2>
          <p className="mt-4 text-sm">{t("home.supportBody")}</p>
          <div className="mt-5 flex flex-wrap gap-2">
            {email && (
              <a href={`mailto:${email}`} className={linkClass}>
                <Mail size={15} aria-hidden="true" />{t("home.supportEmail")}: <bdi dir="ltr">{email}</bdi>
              </a>
            )}
            {whatsappHref && (
              <a href={whatsappHref} target="_blank" rel="noreferrer noopener" className={linkClass}>
                <MessageCircle size={15} aria-hidden="true" />{t("home.supportWhatsApp")}: <bdi dir="ltr">{whatsapp}</bdi>
              </a>
            )}
            <a href="#contact" className={linkClass}>{t("home.supportForm")}</a>
          </div>
        </div>
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
  const { t, href } = useI18n();
  return (
    <section className="mx-auto max-w-6xl px-4 pb-4 pt-16 sm:px-6">
      <div className="relative overflow-hidden rounded-card bg-ink px-6 py-12 text-center text-paper shadow-card sm:px-12 sm:py-16">
        <div className="pointer-events-none absolute -end-24 -top-24 h-72 w-72 rounded-full bg-accent/30 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-24 -start-24 h-72 w-72 rounded-full bg-accent/20 blur-3xl" />
        <h2 className="relative font-display text-2xl font-bold tracking-tight sm:text-4xl">{t("home.finalTitle")}</h2>
        <p className="relative mx-auto mt-3 max-w-xl text-paper/70">{t("home.finalBody")}</p>
        <div className="relative mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <Link href={href("/register")} className="w-full rounded-control bg-accent px-6 py-3 font-medium text-white hover:bg-accent-strong sm:w-auto">{t("home.finalPrimary")}</Link>
          <a href="#contact" className="w-full rounded-control border border-white/20 px-6 py-3 font-medium text-paper hover:bg-white/10 sm:w-auto">{t("home.finalSecondary")}</a>
        </div>
      </div>
    </section>
  );
}

function PricingPreview() {
  const { t, href } = useI18n();
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
          <Link href={href("/pricing")} className="inline-flex items-center gap-2 rounded-control border border-line bg-paper px-5 py-3 font-medium text-ink hover:border-accent">
            {t("pricing.seeAll")}
          </Link>
        </div>
      </div>
    </section>
  );
}

// Visible labels (not placeholder-only) so a field keeps its name once filled.
const CONTACT_LABEL = "mb-1.5 block text-sm font-medium text-ink";
const CONTACT_INPUT = "w-full rounded-control border border-line bg-paper px-3 py-3 text-ink outline-none placeholder:text-muted focus:border-accent focus-visible:ring-2 focus-visible:ring-accent/40";

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
        name: form.get("name"), phone: form.get("phone"), email: form.get("email"),
        preferred_channel: form.get("preferred_channel") || "whatsapp",
        message: form.get("message"), website: form.get("website") });
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
              <label className="block">
                <span className={CONTACT_LABEL}>{t("landing.contactName")}</span>
                <input required name="name" maxLength={255} autoComplete="name" className={CONTACT_INPUT} />
              </label>
              <label className="block">
                <span className={CONTACT_LABEL}>{t("landing.contactPhone")}</span>
                <input
                  type="tel" name="phone" maxLength={32} required inputMode="tel" dir="ltr" autoComplete="tel"
                  className={`${CONTACT_INPUT} text-start`}
                />
              </label>
            </div>
            <label className="block">
              <span className={CONTACT_LABEL}>{t("landing.contactEmailOptional")}</span>
              <input type="email" name="email" maxLength={254} dir="ltr" autoComplete="email" className={`${CONTACT_INPUT} text-start`} />
            </label>
            <fieldset className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
              <legend className="mb-2 font-medium text-ink">{t("landing.contactChannel")}</legend>
              {["whatsapp", "call", "email"].map((channel) => (
                <label key={channel} className="inline-flex cursor-pointer items-center gap-2">
                  <input type="radio" name="preferred_channel" value={channel} defaultChecked={channel === "whatsapp"} className="accent-accent" />
                  {t(`landing.channels.${channel}`)}
                </label>
              ))}
            </fieldset>
            <label className="block">
              <span className={CONTACT_LABEL}>{t("landing.contactMessage")}</span>
              <textarea rows={4} name="message" maxLength={4000} className={CONTACT_INPUT} />
            </label>
            <button
              type="submit" disabled={busy}
              className="w-full rounded-control bg-accent py-3 font-medium text-white hover:bg-accent-strong"
            >
              {busy ? t("improvements.contactSending") : t("landing.contactSend")}
            </button>
          </form>
        )}
        <DirectWhatsAppLink />
      </div>
    </section>
  );
}

export default function LandingPage() {
  return (
    <SiteContactProvider>
      <div className="min-h-screen bg-paper text-ink">
        <MarketingHeader />
        <main>
          <Hero />
          <TrustStrip />
          <Modules />
          <MultiBranch />
          <SudanFit />
          <Stories />
          <Showcase />
          <HowItWorks />
          <TrustSupport />
          <PricingPreview />
          <Faq />
          <FinalCta />
          <ContactCTA />
        </main>
        <MarketingFooter />
        <WhatsAppFloat />
      </div>
    </SiteContactProvider>
  );
}
