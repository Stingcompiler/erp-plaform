"use client";

// Public landing page for the hosted product. Every screenshot is a real
// capture of a local seed_demo company in the page's language and theme
// (lib/marketingShots.js), so the copy next to it describes what the visitor
// is actually looking at.
//
// On a phone a way to start is never far: the hero, a short trial band after
// the modules and another after the branches/Sudan sections, then the closing
// choice between the trial and a walkthrough, with the form.

import { useRef, useSyncExternalStore } from "react";
import Link from "next/link";
import {
  ArrowRight,
  Banknote,
  Briefcase,
  Building2,
  ChartColumn,
  Check,
  ChevronDown,
  Contact,
  DatabaseBackup,
  Languages,
  LifeBuoy,
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

import { MarketingFooter, MarketingHeader } from "@/components/marketing/Chrome";
import { ContactChannels, SiteContactProvider, WhatsAppFloat } from "@/components/marketing/SiteContact";
import DemoRequestForm from "@/components/marketing/DemoRequestForm";
import PlanCards from "@/components/marketing/PlanCards";
import Shot from "@/components/marketing/Shot";
import BranchFlow from "@/components/marketing/BranchFlow";
import { HERO_ARM } from "@/components/landing/heroScripts";
import { heroTiming, revealStyle } from "@/lib/motion";
import { useRevealOnce } from "@/lib/useRevealOnce";

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

// The screenshot beside each story (lib/marketingShots.js names).
const STORY_SHOTS = ["pos", "inventory", "debts"];
const HALF_WIDTH = "(min-width: 1152px) 524px, (min-width: 1024px) calc(50vw - 52px), (min-width: 640px) calc(100vw - 48px), calc(100vw - 32px)";

// A card or block that fades up once as it scrolls into view. Visible in
// the HTML; useRevealOnce (on <main>) arms it only if it is below the fold.
// `index` staggers the cards of one group (lib/motion.js revealDelay).
function Reveal({ children, index = 0, className = "" }) {
  return (
    <div className={`mk-reveal ${className}`} style={revealStyle(index)}>
      {children}
    </div>
  );
}

// Details a visitor can open: a native <details>, so it works without JS,
// is announced as a disclosure and opens with Enter or Space. The summary
// is a 44 px target.
function Disclosure({ summary, children, className = "" }) {
  return (
    <details className={`group ${className}`}>
      <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-2 rounded-control text-sm font-medium text-accent marker:content-none hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40">
        {summary}
        <ChevronDown size={16} aria-hidden="true" className="shrink-0 transition-transform group-open:rotate-180" />
      </summary>
      {children}
    </details>
  );
}

// A short prompt to start between sections: one line and the two ways in.
function TrialBand({ text }) {
  const { t, href } = useI18n();
  return (
    <div className="mx-auto max-w-6xl px-4 sm:px-6">
      <div className="flex flex-col items-center gap-4 rounded-card border border-accent/30 bg-accent/5 px-5 py-6 text-center sm:flex-row sm:justify-between sm:px-8 sm:text-start">
        <p className="font-display text-lg font-semibold text-ink">{text}</p>
        <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:gap-3">
          <Link href={href("/register")} className="inline-flex min-h-11 items-center justify-center whitespace-nowrap rounded-control bg-accent px-5 py-2.5 font-medium text-white shadow-card hover:bg-accent-strong">
            {t("home.heroPrimary")}
          </Link>
          <a href="#walkthrough" className="inline-flex min-h-11 items-center justify-center whitespace-nowrap rounded-control border border-line bg-surface px-5 py-2.5 font-medium text-ink hover:border-accent">
            {t("home.finalSecondary")}
          </a>
        </div>
      </div>
    </div>
  );
}

// The headline, subtitle and buttons are plain HTML at first paint. The
// headline never moves; the short entrance of the other parts is CSS armed
// by the inline script in heroScripts.js (the "Public site motion" block in
// app/globals.css).
const noSubscribe = () => () => {};

function Hero() {
  const { t, href } = useI18n();
  // True in the exported HTML and while hydrating it, false on a
  // client-side render: the scripts only belong in the page as loaded (a
  // script React creates would never run anyway).
  const fromHtml = useSyncExternalStore(noSubscribe, () => false, () => true);
  return (
    <section className="relative overflow-hidden">
      <div className="pointer-events-none absolute inset-0 -z-10 bg-gradient-to-b from-accent/10 via-transparent to-transparent" />
      <div className="pointer-events-none absolute start-1/2 top-24 -z-10 h-[480px] w-[900px] -translate-x-1/2 rounded-full bg-accent/10 blur-3xl" />
      <div className="mx-auto max-w-6xl px-4 pb-10 pt-14 sm:px-6 sm:pt-20">
        <div className="mx-auto max-w-3xl text-center">
          <span className="inline-flex items-center rounded-full border border-line bg-surface px-3 py-1 text-xs font-medium text-muted">
            {t("home.heroBadge")}
          </span>
          <h1 className="mt-5 text-balance font-display text-3xl font-bold leading-[1.2] tracking-tight sm:text-5xl">
            {t("home.heroTitle")}
          </h1>
          {/* After the headline, so the first frame the browser paints while
              it waits on this script already has the header, badge and h1. */}
          {fromHtml && <script dangerouslySetInnerHTML={{ __html: HERO_ARM }} />}
          <p className="hero-fade mx-auto mt-5 max-w-2xl text-base text-muted sm:text-lg" style={heroTiming("subtitle")}>{t("home.heroSubtitle")}</p>
          <p className="hero-fade mx-auto mt-4 flex max-w-2xl items-start justify-center gap-2 text-sm text-ink/80" style={heroTiming("offline")}>
            <WifiOff size={16} aria-hidden="true" className="mt-0.5 shrink-0 text-accent" />
            <span>{t("home.heroOffline")}</span>
          </p>
          <div className="hero-fade" style={heroTiming("actions")}>
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
          </div>
        </div>
        <div className="mx-auto mt-12 max-w-5xl">
          <div className="hero-shot" style={heroTiming("shot")}>
            <Shot name="dashboard" alt={t("home.heroCaption")} priority sizes="(min-width: 1072px) 1022px, (min-width: 640px) calc(100vw - 48px), calc(100vw - 32px)" />
          </div>
          <p className="mt-3 text-center text-xs text-muted">{t("home.heroCaption")}</p>
        </div>
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
      <div className="mx-auto grid max-w-6xl grid-cols-2 gap-3 px-4 py-5 sm:px-6 sm:py-6 lg:grid-cols-4">
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
  const { t, href } = useI18n();
  const stories = t("home.stories");
  if (!Array.isArray(stories)) return null;
  return (
    <section id="features" className="mx-auto max-w-6xl border-t border-line px-4 py-12 sm:px-6 sm:py-24">
      <h2 className="text-center font-display text-2xl font-bold tracking-tight sm:text-3xl">{t("home.storiesTitle")}</h2>
      <div className="mt-10 space-y-14 sm:mt-14 sm:space-y-20">
        {stories.map((story, index) => {
          const shot = STORY_SHOTS[index] || STORY_SHOTS[0];
          const flip = index % 2 === 1;
          return (
            <Reveal key={story.title}>
              <div className={`grid items-center gap-8 lg:grid-cols-2 lg:gap-14 ${flip ? "lg:[&>*:first-child]:order-2" : ""}`}>
                <div>
                  <p className="text-sm font-semibold uppercase tracking-wide text-accent">{story.eyebrow}</p>
                  <h3 className="mt-2 font-display text-2xl font-bold tracking-tight sm:text-3xl">{story.title}</h3>
                  <ul className="mt-5 space-y-2.5">
                    {story.bullets.map((line) => (
                      <li key={line} className="flex items-start gap-2 text-sm sm:text-base">
                        <Check size={18} className="mt-0.5 shrink-0 text-accent" />
                        <span>{line}</span>
                      </li>
                    ))}
                  </ul>
                </div>
                <Shot name={shot} alt={story.title} sizes={HALF_WIDTH} />
              </div>
            </Reveal>
          );
        })}
      </div>
      <div className="mt-12 text-center">
        <Link href={href("/register")} className="inline-flex min-h-11 items-center justify-center rounded-control bg-accent px-6 py-3 font-medium text-white shadow-card hover:bg-accent-strong">
          {t("home.heroPrimary")}
        </Link>
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
    <section id="modules" className="mx-auto max-w-6xl px-4 py-12 sm:px-6 sm:py-24">
      <div className="mx-auto max-w-2xl text-center">
        <h2 className="font-display text-2xl font-bold tracking-tight sm:text-3xl">{t("home.modulesTitle")}</h2>
        <p className="mt-3 text-muted">{t("home.modulesSubtitle")}</p>
      </div>
      <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {modules.map((module, index) => {
          const Icon = MODULE_ICONS[module.key] || Package;
          return (
            <Reveal key={module.key} index={index % 4} className="h-full">
              {/* On a phone the icon sits beside the text (a shorter card, so
                  the next way to start is closer); from sm up, above it. */}
              <Link
                href={href(`/product#${module.anchor}`)}
                className="group flex h-full gap-4 rounded-card border border-line bg-surface p-4 shadow-card transition-colors hover:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 sm:flex-col sm:gap-0 sm:p-5"
              >
                <span className="grid h-10 w-10 shrink-0 place-items-center rounded-control bg-accent/10 text-accent"><Icon size={20} aria-hidden="true" /></span>
                <div className="flex flex-1 flex-col">
                  <h3 className="font-display text-lg font-semibold sm:mt-4">{module.title}</h3>
                  <p className="mt-1 flex-1 text-sm text-muted sm:mt-2">{module.body}</p>
                  <span className="mt-4 hidden items-center gap-1 text-sm font-medium text-accent sm:inline-flex">
                    {t("home.modulesMore")}
                    <ArrowRight size={15} aria-hidden="true" className="transition-transform group-hover:translate-x-0.5 rtl:rotate-180 rtl:group-hover:-translate-x-0.5" />
                  </span>
                </div>
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
        <BranchFlow className="mt-10" />
        <div className="mt-10 grid gap-5 lg:grid-cols-3">
          <Reveal className="h-full">
            <div className={card}>
              <h3 className={heading}><Building2 size={20} aria-hidden="true" className="shrink-0 text-accent" />{t("home.multiBranchTitle")}</h3>
              <p className="mt-3 text-sm text-muted">{t("home.multiBranchBody")}</p>
            </div>
          </Reveal>
          <Reveal index={1} className="h-full">
            <div className={card}>
              <h3 className={heading}><Users size={20} aria-hidden="true" className="shrink-0 text-accent" />{t("home.multiRolesTitle")}</h3>
              <p className="mt-3 text-sm text-muted">{t("home.multiRolesBody")}</p>
              {Array.isArray(roles) && (
                <Disclosure summary={t("home.multiRolesShow")} className="mt-2">
                  <ul className="mt-2 flex flex-wrap gap-2">
                    {roles.map((role) => (
                      <li key={role} className="rounded-full border border-line bg-surface px-3 py-1 text-xs font-medium text-ink">{role}</li>
                    ))}
                  </ul>
                </Disclosure>
              )}
            </div>
          </Reveal>
          <Reveal index={2} className="h-full">
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
    <section id="sudan" className="mx-auto max-w-6xl px-4 py-12 sm:px-6 sm:py-24">
      <h2 className="text-center font-display text-2xl font-bold tracking-tight sm:text-3xl">{t("home.sudanTitle")}</h2>
      <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {items.map(([title, body], index) => {
          const Icon = SUDAN_ICONS[index] || Check;
          return (
            <Reveal key={title} index={index} className="h-full">
              <div className="h-full rounded-card border border-line bg-paper p-4 shadow-card sm:p-5">
                <div className="flex items-center gap-3 sm:block">
                  <span className="grid h-9 w-9 shrink-0 place-items-center rounded-control bg-accent/10 text-accent"><Icon size={18} aria-hidden="true" /></span>
                  <h3 className="font-display font-semibold sm:mt-3">{title}</h3>
                </div>
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
  const { t, href } = useI18n();
  const steps = t("home.how");
  if (!Array.isArray(steps)) return null;
  return (
    <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-24">
      <h2 className="text-center font-display text-2xl font-bold tracking-tight sm:text-3xl">{t("home.howTitle")}</h2>
      <div className="mt-10 grid gap-5 md:grid-cols-3">
        {steps.map(([title, body], index) => (
          <Reveal key={title} index={index}>
            <div className="h-full rounded-card border border-line bg-paper p-6 shadow-card">
              <span className="grid h-9 w-9 place-items-center rounded-full bg-accent font-display text-sm font-bold text-white">{index + 1}</span>
              <h3 className="mt-4 font-display text-lg font-semibold">{title}</h3>
              <p className="mt-2 text-sm text-muted">{body}</p>
            </div>
          </Reveal>
        ))}
      </div>
      <div className="mt-8 text-center">
        <Link href={href("/register")} className="inline-flex min-h-11 items-center justify-center rounded-control bg-accent px-6 py-3 font-medium text-white shadow-card hover:bg-accent-strong">
          {t("home.heroPrimary")}
        </Link>
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
  const points = t("home.backupPoints");
  const more = t("home.backupMore");
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
          {Array.isArray(more) && (
            <Disclosure summary={t("home.backupMoreTitle")} className="mt-3">
              <ul className="mt-2 space-y-2.5 text-sm text-muted">
                {more.map((line) => (
                  <li key={line} className="flex items-start gap-2">
                    <Check size={16} aria-hidden="true" className="mt-0.5 shrink-0 text-accent" /><span>{line}</span>
                  </li>
                ))}
              </ul>
            </Disclosure>
          )}
        </div>
        <div className="rounded-card border border-line bg-surface p-6 shadow-card">
          <h2 className="flex items-center gap-2 font-display text-xl font-bold">
            <LifeBuoy size={20} aria-hidden="true" className="text-accent" />{t("home.supportTitle")}
          </h2>
          <p className="mt-4 text-sm">{t("home.supportBody")}</p>
          <a href="#walkthrough" className="mt-5 inline-flex min-h-11 items-center gap-2 rounded-control bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-strong">
            {t("home.supportForm")}
          </a>
          <ContactChannels lead={t("home.supportDirect")} className="mt-5" />
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
            // The padding is on the summary, so the whole card head is the
            // tap target (44 px and up), not just the line of text.
            <details key={question} className="group rounded-card border border-line bg-paper">
              <summary className="flex min-h-11 cursor-pointer list-none items-center rounded-card p-5 font-medium marker:content-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40">{question}</summary>
              <p className="-mt-2 px-5 pb-5 text-sm text-muted">{answer}</p>
            </details>
          ))}
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

// The close of the page, in one section: a short choice between starting
// the trial and asking for a walkthrough, then the walkthrough form under its
// own heading (the form and its error handling: DemoRequestForm.jsx).
function GetStarted() {
  const { t, href } = useI18n();
  return (
    <section id="contact" className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-24">
      <div className="relative overflow-hidden rounded-card bg-ink px-6 py-10 text-paper shadow-card sm:px-12 sm:py-14">
        <div className="pointer-events-none absolute -end-24 -top-24 h-72 w-72 rounded-full bg-accent/30 blur-3xl" />
        <h2 className="relative text-center font-display text-2xl font-bold tracking-tight sm:text-4xl">{t("home.finalTitle")}</h2>
        <div className="relative mx-auto mt-8 grid max-w-3xl gap-4 sm:grid-cols-2">
          <div className="flex flex-col rounded-card border border-paper/15 bg-paper/5 p-5">
            <p className="flex-1 text-sm text-paper/80">{t("home.startTrialBody")}</p>
            <Link href={href("/register")} className="mt-4 inline-flex min-h-11 items-center justify-center rounded-control bg-accent px-5 py-3 font-medium text-white hover:bg-accent-strong">
              {t("home.finalPrimary")}
            </Link>
          </div>
          <div className="flex flex-col rounded-card border border-paper/15 bg-paper/5 p-5">
            <p className="flex-1 text-sm text-paper/80">{t("home.startWalkBody")}</p>
            <a href="#walkthrough" className="mt-4 inline-flex min-h-11 items-center justify-center rounded-control border border-paper/25 px-5 py-3 font-medium text-paper hover:bg-paper/10">
              {t("home.finalSecondary")}
            </a>
          </div>
        </div>
      </div>
      <div id="walkthrough" className="mx-auto mt-8 max-w-3xl scroll-mt-20 rounded-card border border-line bg-surface p-6 shadow-card sm:p-10">
        <div className="text-center">
          <h3 className="font-display text-2xl font-bold tracking-tight">{t("home.formTitle")}</h3>
          <p className="mx-auto mt-2 max-w-xl text-sm text-muted">{t("home.formBody")}</p>
        </div>
        <DemoRequestForm />
      </div>
    </section>
  );
}

export default function LandingPage() {
  const { t } = useI18n();
  const mainRef = useRef(null);
  useRevealOnce(mainRef);
  return (
    <SiteContactProvider>
      <div className="min-h-screen bg-paper text-ink">
        <MarketingHeader />
        <main ref={mainRef} id="content" tabIndex={-1} className="focus:outline-none">
          <Hero />
          <TrustStrip />
          <Modules />
          <TrialBand text={t("home.bandModules")} />
          <MultiBranch />
          <SudanFit />
          <TrialBand text={t("home.bandBranches")} />
          <Stories />
          <Showcase />
          <HowItWorks />
          <TrustSupport />
          <PricingPreview />
          <Faq />
          <GetStarted />
        </main>
        <MarketingFooter />
        <WhatsAppFloat />
      </div>
    </SiteContactProvider>
  );
}
