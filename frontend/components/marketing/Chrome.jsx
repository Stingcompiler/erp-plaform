"use client";

// Shared chrome for every public (logged-out) page: the marketing header with
// language/theme toggles, the footer, and the wrapper that sends visitors of
// a standalone server to sign-in — there is nothing to market there.

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Languages, Menu, MoonStar, Sun, SunMoon, X } from "lucide-react";

import { useAuth } from "../../app/providers/AuthProvider";
import { useI18n } from "../../app/providers/I18nProvider";
import { DEMO_URL, HAS_LIVE_DEMO } from "@/lib/demo";
import { publicSite } from "@/lib/api";
import { GUIDES } from "@/lib/content/guides";
import { SOLUTIONS } from "@/lib/content/solutions";
import { cachedDeploymentMode, fetchDeploymentMode } from "@/lib/deploymentMode";
import VezanoMark from "@/components/brand/VezanoMark";

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

// Absolute paths so the links work from /pricing and /register as well as
// from the landing page itself.
const NAV_LINKS = [
  ["/product", "landing.navFeatures"],
  ["/solutions", "landing.navSolutions"],
  ["/guides", "landing.navGuides"],
  ["/pricing", "landing.navPricing"],
  ["/#contact", "landing.navContact"],
];

// The stores directory joins the header only once there is enough in it to
// impress: a link to a near-empty directory reads as "no customers". The
// footer links it always (crawlers and the curious still find it).
const STORES_NAV_MIN = 3;
const STORES_PATH = "/s/";

function useStoresNav() {
  const [count, setCount] = useState(0);
  useEffect(() => {
    let cancelled = false;
    publicSite
      .showcase()
      .then((response) => { if (!cancelled) setCount((response.data.sites || []).length); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);
  return count >= STORES_NAV_MIN;
}

export function MarketingHeader() {
  const { t, href } = useI18n();
  const showStores = useStoresNav();
  // The directory is a Django page on the same origin, not a Next route, so
  // it is never language-prefixed.
  const navLinks = showStores ? [...NAV_LINKS, [STORES_PATH, "landing.navStores"]] : NAV_LINKS;
  const navHref = (path) => (path === STORES_PATH ? path : href(path));
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
      href={HAS_LIVE_DEMO ? DEMO_URL : href(DEMO_URL)}
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
        <Link href={href("/")} className="flex shrink-0 items-center gap-2 font-display text-lg font-bold tracking-tight">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-accent text-white"><VezanoMark size={20} /></span>
          {t("common.appName")}
        </Link>
        <nav className="hidden items-center gap-6 text-sm text-muted md:flex">
          {navLinks.map(([path, key]) => (
            <a key={path} href={navHref(path)} className="hover:text-ink">{t(key)}</a>
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
            {navLinks.map(([path, key]) => (
              <a
                key={path}
                href={navHref(path)}
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

export function MarketingFooter() {
  const { t, href, language } = useI18n();
  const contentLanguage = language === "en" ? "en" : "ar";
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
          <div className="flex flex-wrap gap-x-12 gap-y-8">
            <div>
              <div className="text-sm font-semibold text-paper/90">
                {t("landing.footerSolutions")}
              </div>
              <ul className="mt-3 space-y-2 text-sm text-paper/60">
                {SOLUTIONS.map((item) => (
                  <li key={item.slug}><Link href={href(`/solutions/${item.slug}`)} className="hover:text-paper">{item[contentLanguage].title}</Link></li>
                ))}
              </ul>
            </div>
            <div>
              <div className="text-sm font-semibold text-paper/90">
                {t("landing.footerLearn")}
              </div>
              <ul className="mt-3 space-y-2 text-sm text-paper/60">
                {GUIDES.map((item) => (
                  <li key={item.slug}><Link href={href(`/guides/${item.slug}`)} className="hover:text-paper">{item[contentLanguage].title}</Link></li>
                ))}
                <li><Link href={href("/compare/excel-and-paper")} className="hover:text-paper">{t("content.compareEyebrow")}</Link></li>
                <li><a href={STORES_PATH} className="hover:text-paper">{t("landing.navStores")}</a></li>
              </ul>
            </div>
            <div>
              <div className="text-sm font-semibold text-paper/90">
                {t("landing.footerProduct")}
              </div>
              <ul className="mt-3 space-y-2 text-sm text-paper/60">
                <li><Link href={href("/product")} className="hover:text-paper">{t("landing.navFeatures")}</Link></li>
                <li><Link href={href("/#modules")} className="hover:text-paper">{t("landing.navModules")}</Link></li>
                <li><Link href={href("/pricing")} className="hover:text-paper">{t("landing.navPricing")}</Link></li>
                <li><Link href="/login" className="hover:text-paper">{t("common.signIn")}</Link></li>
              </ul>
            </div>
            <div>
              <div className="text-sm font-semibold text-paper/90">
                {t("landing.footerCompany")}
              </div>
              <ul className="mt-3 space-y-2 text-sm text-paper/60">
                <li><Link href={href("/#contact")} className="hover:text-paper">{t("landing.navContact")}</Link></li>
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


// Wraps a public page. On a standalone installation the public surface does
// not exist, so the visitor is sent to sign-in before anything renders.
export function MarketingPage({ children }) {
  const router = useRouter();
  const [mode, setMode] = useState(cachedDeploymentMode());

  useEffect(() => {
    let cancelled = false;
    fetchDeploymentMode().then((value) => { if (!cancelled) setMode(value); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (mode === "standalone") router.replace("/login");
  }, [mode, router]);

  if (mode === "standalone") return null;
  return (
    <div className="min-h-screen bg-paper text-ink">
      <MarketingHeader />
      <main>{children}</main>
      <MarketingFooter />
    </div>
  );
}
