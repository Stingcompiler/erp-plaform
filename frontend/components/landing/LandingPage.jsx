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

import { demoRequests, registration } from "@/lib/api";
import { DEMO_URL, HAS_LIVE_DEMO } from "@/lib/demo";
import VezanoMark from "@/components/brand/VezanoMark";

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

const NAV_LINKS = [
  ["#features", "landing.navFeatures"],
  ["#modules", "landing.navModules"],
  ["#pricing", "landing.navPricing"],
  ["#contact", "landing.navContact"],
];

function Header() {
  const { t } = useI18n();
  const { user } = useAuth();
  const [open, setOpen] = useState(false);

  // The phone menu is a plain disclosure: no focus trap, but it closes on
  // Escape and whenever the viewport grows past the breakpoint that shows
  // the inline nav, so it can't linger open behind the desktop layout.
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event) => event.key === "Escape" && setOpen(false);
    const media = window.matchMedia("(min-width: 768px)");
    const onMedia = (event) => event.matches && setOpen(false);
    window.addEventListener("keydown", onKey);
    media.addEventListener("change", onMedia);
    return () => {
      window.removeEventListener("keydown", onKey);
      media.removeEventListener("change", onMedia);
    };
  }, [open]);

  const signIn = (
    <Link
      href={user ? "/dashboard" : "/login"}
      className="inline-flex h-10 shrink-0 items-center whitespace-nowrap rounded-control bg-accent px-3.5 text-sm font-medium text-white hover:bg-accent-strong"
    >
      {user ? t("nav.dashboard") : t("common.signIn")}
    </Link>
  );
  const trial = (className) => (
    <a
      href={DEMO_URL}
      target={HAS_LIVE_DEMO ? "_blank" : undefined}
      rel={HAS_LIVE_DEMO ? "noreferrer" : undefined}
      onClick={() => setOpen(false)}
      className={className}
    >
      {t(HAS_LIVE_DEMO ? "landing.heroCtaDemo" : "landing.heroCtaTrial")}
    </a>
  );

  return (
    <header className="sticky top-0 z-30 border-b border-line/70 bg-paper/80 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-2 px-4 sm:px-6">
        <Link href="/" className="flex shrink-0 items-center gap-2 font-display text-lg font-bold tracking-tight">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-accent text-white"><VezanoMark size={20} /></span>
          {t("common.appName")}
        </Link>
        <nav className="hidden items-center gap-6 text-sm text-muted md:flex">
          {NAV_LINKS.map(([href, key]) => (
            <a key={href} href={href} className="hover:text-ink">{t(key)}</a>
          ))}
        </nav>
        {/* Desktop / tablet: everything inline. */}
        <div className="hidden items-center gap-1 md:flex">
          <LangToggle />
          <ThemeToggle />
          {trial("ms-1 inline-flex h-10 items-center whitespace-nowrap rounded-control border border-line bg-surface px-3.5 text-sm font-medium text-ink hover:border-accent")}
          <span className="ms-1">{signIn}</span>
        </div>
        {/* Phone: sign-in stays visible; the rest lives behind the menu. */}
        <div className="flex items-center gap-1 md:hidden">
          {signIn}
          <button
            type="button"
            aria-expanded={open}
            aria-controls="landing-menu"
            aria-label={t("shell.menu")}
            onClick={() => setOpen((value) => !value)}
            className="grid h-10 w-10 place-items-center rounded-control text-ink hover:bg-surface"
          >
            {open ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
      </div>
      {open && (
        <div id="landing-menu" className="border-t border-line/70 bg-paper md:hidden">
          <nav className="mx-auto flex max-w-6xl flex-col px-4 py-2 text-base">
            {NAV_LINKS.map(([href, key]) => (
              <a
                key={href}
                href={href}
                onClick={() => setOpen(false)}
                className="rounded-control px-2 py-3 text-ink hover:bg-surface"
              >
                {t(key)}
              </a>
            ))}
            <div className="my-2 border-t border-line/70" />
            {trial("rounded-control border border-line bg-surface px-4 py-3 text-center font-medium text-ink hover:border-accent")}
            <div className="mt-2 flex items-center justify-between px-1 pb-2">
              <LangToggle />
              <ThemeToggle />
            </div>
          </nav>
        </div>
      )}
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
              href="#trial"
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

function PricingAndTrial() {
  const { t } = useI18n();
  const [plans, setPlans] = useState([]);
  const [sent, setSent] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const requestId = useRef(null);

  useEffect(() => {
    registration.publicPlans().then((response) => setPlans(response.data)).catch(() => setPlans([]));
  }, []);

  async function onSubmit(event) {
    event.preventDefault();
    if (busy) return;
    const form = new FormData(event.currentTarget);
    requestId.current ||= crypto.randomUUID();
    setBusy(true); setError("");
    try {
      const response = await registration.create({
        request_uuid: requestId.current,
        company_name: form.get("company_name"),
        contact_name: form.get("contact_name"),
        email: form.get("email"),
        phone: form.get("phone"),
        country: form.get("country").toUpperCase(),
        timezone_name: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
        estimated_users: Number(form.get("estimated_users")) || undefined,
        estimated_branches: Number(form.get("estimated_branches")) || undefined,
        delivery_mode: "saas",
        plan_version: Number(form.get("plan_version")),
        message: form.get("message"),
        privacy_version: "2026-09",
      });
      setSent(response.data.reference);
    } catch {
      setError(t("registration.publicError"));
    } finally { setBusy(false); }
  }

  return (
    <section id="pricing" className="border-t border-line bg-surface">
      <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-24">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="font-display text-2xl font-bold tracking-tight sm:text-3xl">{t("registration.title")}</h2>
          <p className="mt-3 text-muted">{t("registration.subtitle")}</p>
        </div>
        <div className="mt-10 grid gap-5 md:grid-cols-3">
          {plans.length ? plans.map((plan) => (
            <article key={plan.id} className="rounded-card border border-line bg-paper p-6 shadow-card">
              <h3 className="font-display text-lg font-semibold">{plan.plan_name}</h3>
              <p className="mt-2 text-2xl font-bold text-accent">{plan.price} <span className="text-sm font-medium">{plan.currency}</span></p>
              <p className="mt-1 text-sm text-muted">{t("registration.billing", { cycle: plan.billing_cycle })}</p>
              <p className="mt-5 text-sm text-muted">{plan.modules.join(" · ")}</p>
            </article>
          )) : <p className="text-center text-muted md:col-span-3">{t("registration.quoteOnly")}</p>}
        </div>
        <div id="trial" className="mx-auto mt-10 max-w-3xl rounded-card border border-line bg-paper p-6 shadow-card sm:p-8">
          <h3 className="font-display text-xl font-semibold">{t("registration.formTitle")}</h3>
          <p className="mt-2 text-sm text-muted">{t("registration.formSubtitle")}</p>
          {plans[0]?.trial_days > 0 && <p className="mt-2 inline-block rounded-control bg-accent/10 px-3 py-1.5 text-sm font-medium text-accent">{t("registration.trialLength", { days: plans[0].trial_days })}</p>}
          {sent ? <p className="mt-6 rounded-control bg-ok/10 p-4 text-center font-medium text-ok">{t("registration.sent")}<span className="mt-1 block text-xs">{sent}</span></p> : (
            <form onSubmit={onSubmit} className="mt-6 space-y-4">
              {error && <p role="alert" className="text-sm text-danger">{error}</p>}
              <div className="grid gap-4 sm:grid-cols-2">
                <input required name="company_name" maxLength={255} placeholder={t("registration.companyName")} className="rounded-control border border-line bg-surface px-3 py-3 outline-none focus:border-accent" />
                <input required name="contact_name" maxLength={255} placeholder={t("registration.contactName")} className="rounded-control border border-line bg-surface px-3 py-3 outline-none focus:border-accent" />
                <input required type="email" name="email" maxLength={254} placeholder={t("registration.email")} className="rounded-control border border-line bg-surface px-3 py-3 outline-none focus:border-accent" />
                <input required name="phone" maxLength={64} placeholder={t("registration.phone")} className="rounded-control border border-line bg-surface px-3 py-3 outline-none focus:border-accent" />
                <input required name="country" minLength={2} maxLength={2} placeholder={t("registration.country")} className="rounded-control border border-line bg-surface px-3 py-3 uppercase outline-none focus:border-accent" />
                <select required name="plan_version" defaultValue="" className="rounded-control border border-line bg-surface px-3 py-3 outline-none focus:border-accent">
                  <option value="" disabled>{t("registration.plan")}</option>
                  {plans.map((plan) => <option key={plan.id} value={plan.id}>{plan.plan_name} · {plan.price} {plan.currency}</option>)}
                </select>
                <input type="number" min="1" name="estimated_users" placeholder={t("registration.estimatedUsers")} className="rounded-control border border-line bg-surface px-3 py-3 outline-none focus:border-accent" />
                <input type="number" min="1" name="estimated_branches" placeholder={t("registration.estimatedBranches")} className="rounded-control border border-line bg-surface px-3 py-3 outline-none focus:border-accent" />
              </div>
              <textarea rows={3} name="message" maxLength={4000} placeholder={t("registration.message")} className="w-full rounded-control border border-line bg-surface px-3 py-3 outline-none focus:border-accent" />
              <p className="text-xs text-muted">{t("registration.privacy")}</p>
              <button type="submit" disabled={busy || plans.length === 0} className="w-full rounded-control bg-accent py-3 font-medium text-white hover:bg-accent-strong disabled:opacity-50">
                {busy ? t("registration.sending") : t("registration.submit")}
              </button>
            </form>
          )}
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

function Footer() {
  const { t } = useI18n();
  const year = new Date().getFullYear();
  return (
    <footer className="border-t border-line bg-ink text-paper">
      <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6">
        <div className="flex flex-col gap-8 sm:flex-row sm:justify-between">
          <div className="max-w-xs">
            <div className="flex items-center gap-2 font-display text-lg font-bold tracking-tight">
              <span className="grid h-8 w-8 place-items-center rounded-lg bg-accent text-white"><VezanoMark size={20} /></span>
              {t("common.appName")}
            </div>
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
          © {year} {t("common.appName")}. {t("landing.footerRights")}
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
        <PricingAndTrial />
        <ContactCTA />
      </main>
      <Footer />
    </div>
  );
}
