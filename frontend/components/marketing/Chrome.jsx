"use client";

// Shared chrome for every public (logged-out) page: the marketing header with
// language/theme toggles, the footer, and the wrapper that sends visitors of
// a standalone server to sign-in — there is nothing to market there.

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Languages, MoonStar, Sun, SunMoon } from "lucide-react";

import { useAuth } from "../../app/providers/AuthProvider";
import { useI18n } from "../../app/providers/I18nProvider";
import { DEMO_URL, HAS_LIVE_DEMO } from "@/lib/demo";
import { publicSite } from "@/lib/api";
import { GUIDE_TITLES, SOLUTION_TITLES } from "@/lib/content/titles";
import { cachedDeploymentMode, fetchDeploymentMode } from "@/lib/deploymentMode";
import { NAV_MOTION, isCurrentMarketingLink, menuItemStyle } from "@/lib/navMotion";
import { usePresence } from "@/lib/usePresence";
import { useScrolledPast } from "@/lib/useScrolledPast";
import { turnIcon } from "@/components/ui/NavMotion";
import LogoMark from "@/components/brand/LogoMark";
import Wordmark from "@/components/brand/Wordmark";
import { SiteContactLines, SiteContactProvider, WhatsAppFloat } from "@/components/marketing/SiteContact";

// The toggles' icons turn in when pressed (components/ui/NavMotion.jsx
// turnIcon): the theme's new icon from a quarter turn back, the language
// globe as the page switches. Only on a press, never on a page load.
function ThemeToggle() {
  const { t, theme, cycleTheme } = useI18n();
  const icon = useRef(null);
  const Icon = theme === "dark" ? MoonStar : theme === "light" ? Sun : SunMoon;
  return (
    <button
      onClick={() => { cycleTheme(); turnIcon(icon.current); }}
      aria-label={t("shell.theme")}
      className="tap grid h-10 w-10 place-items-center rounded-control text-muted hover:bg-surface hover:text-ink"
    >
      <span ref={icon} className="grid place-items-center"><Icon size={18} /></span>
    </button>
  );
}

function LangToggle() {
  const { language, toggleLanguage, t } = useI18n();
  const icon = useRef(null);
  return (
    <button
      onClick={() => { turnIcon(icon.current); toggleLanguage(); }}
      title={t("shell.switchLanguage")}
      className="tap flex h-10 items-center gap-1.5 rounded-control px-2.5 text-sm font-medium text-muted hover:bg-surface hover:text-ink"
    >
      <span ref={icon} className="grid place-items-center"><Languages size={16} /></span>
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

// vezano.app/track/: after the other links; on a narrow desktop header it
// lives in the phone menu and the footer only, so the bar never overflows.
const TRACK_LINK = ["/track", "track.nav", "hidden xl:inline"];

// The company-pages directory (a Django page on the same origin, never
// language-prefixed). The footer links it always; the header names it
// «الشركات والمتاجر» / "Companies & stores" as soon as the showcase lists
// STORES_NAV_MIN sites (owner, 2026-10-01; #221 had kept it to the footer).
const STORES_PATH = "/s/";
const STORES_NAV_MIN = 1;
const STORES_LINK = [STORES_PATH, "landing.navCompanies"];

// One showcase request per page load, shared by every header that mounts.
let showcaseCount = null;
function fetchShowcaseCount() {
  if (!showcaseCount) {
    showcaseCount = publicSite
      .showcase()
      .then((response) => (response.data?.sites || []).length)
      .catch(() => {
        showcaseCount = null;
        return 0;
      });
  }
  return showcaseCount;
}

// null while the showcase is being read, then whether to show the link. The
// header keeps the link's place (invisible) while it is null, so the links
// beside it do not move when it appears.
function useStoresNav() {
  const [show, setShow] = useState(null);
  useEffect(() => {
    let cancelled = false;
    fetchShowcaseCount().then((count) => { if (!cancelled) setShow(count >= STORES_NAV_MIN); });
    return () => { cancelled = true; };
  }, []);
  return show;
}

export function MarketingHeader() {
  const { t, href } = useI18n();
  const showStores = useStoresNav();
  const navLinks = [...NAV_LINKS, ...(showStores === false ? [] : [STORES_LINK]), TRACK_LINK];
  // The directory is a Django page, never language-prefixed.
  const navHref = (path) => (path === STORES_PATH ? path : href(path));
  const pending = (path) => path === STORES_PATH && showStores === null;
  const { user } = useAuth();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  // The phone menu stays mounted (inert) while it folds back up.
  const menu = usePresence(open, NAV_MOTION.menuOut);
  // See-through at the top; blurred paper and a hairline once scrolled.
  const scrolled = useScrolledPast();

  // The phone menu is a plain disclosure: no focus trap, but it closes on
  // Escape and whenever the viewport grows past the breakpoint that shows
  // the inline nav, so it can't linger open behind the desktop layout.
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event) => event.key === "Escape" && setOpen(false);
    const media = window.matchMedia("(min-width: 1024px)");
    const onMedia = (event) => event.matches && setOpen(false);
    window.addEventListener("keydown", onKey);
    media.addEventListener("change", onMedia);
    return () => {
      window.removeEventListener("keydown", onKey);
      media.removeEventListener("change", onMedia);
    };
  }, [open]);

  // prefetch={false}: sign-in and the workspace are app routes (their own
  // JavaScript and the app's dictionary); a visitor reading the landing page
  // should not download them on a slow line just because the link is on
  // screen. They load when clicked.
  const signIn = (
    <Link
      href={user ? "/dashboard" : "/login"}
      prefetch={false}
      className="tap inline-flex h-10 shrink-0 items-center whitespace-nowrap rounded-control bg-accent px-3.5 text-sm font-medium text-white hover:bg-accent-strong"
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
    <header
      data-scrolled={scrolled ? "true" : "false"}
      data-menu={open ? "open" : "closed"}
      className="mk-header sticky top-0 z-30 border-b"
    >
      {/* First stop for the keyboard: straight past the header to the page. */}
      <a
        href="#content"
        className="sr-only rounded-control bg-accent px-4 py-3 text-sm font-medium text-white shadow-card focus:not-sr-only focus:fixed focus:start-3 focus:top-3 focus:z-50 focus:outline-none focus:ring-2 focus:ring-accent/40 focus:ring-offset-2"
      >
        {t("landing.skipToContent")}
      </a>
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-2 px-4 sm:px-6">
        <Link href={href("/")} className="flex min-h-11 shrink-0 items-center gap-2 font-display text-lg font-bold tracking-tight">
          <LogoMark size={32} decorative />
          <Wordmark />
        </Link>
        {/* gap-3 below 1280: with «الشركات والمتاجر» / "Companies & stores"
            the English bar measured 15px clear of the logo and the controls at
            1024 (gap-4 left none, and the link wrapped). */}
        <nav className="hidden items-center gap-3 whitespace-nowrap text-sm text-muted lg:flex xl:gap-6">
          {navLinks.map(([path, key, visibility]) => (
            <a
              key={path}
              href={navHref(path)}
              aria-current={isCurrentMarketingLink(pathname, path) ? "page" : undefined}
              /* Held in place, unseen and unfocusable, until the showcase answers. */
              aria-hidden={pending(path) || undefined}
              tabIndex={pending(path) ? -1 : undefined}
              className={`mk-navlink hover:text-ink ${pending(path) ? "invisible" : ""} ${visibility || ""}`}
            >
              {t(key)}
            </a>
          ))}
        </nav>
        {/* Desktop: everything inline. Tablets use the phone menu — seven links
            and four controls don't fit below 1024px (English overflowed by
            ~200px at 800). */}
        <div className="hidden items-center gap-1 lg:flex">
          <LangToggle />
          <ThemeToggle />
          {trial("ms-1 inline-flex h-10 items-center whitespace-nowrap rounded-control border border-line bg-surface px-3.5 text-sm font-medium text-ink hover:border-accent")}
          <span className="ms-1">{signIn}</span>
        </div>
        {/* Phone and tablet: sign-in stays visible; the rest lives behind the menu. */}
        <div className="flex items-center gap-1 lg:hidden">
          {signIn}
          <button
            type="button"
            aria-expanded={open}
            aria-controls="landing-menu"
            aria-label={t("shell.menu")}
            onClick={() => setOpen((value) => !value)}
            className="tap grid h-10 w-10 place-items-center rounded-control border border-line bg-surface p-2 text-ink hover:border-accent"
          >
            {/* Three lines that fold into an X. */}
            <span className="mk-burger" data-open={open ? "true" : "false"} aria-hidden="true">
              <span /><span /><span />
            </span>
          </button>
        </div>
      </div>
      {menu.mounted && (
        <div
          id="landing-menu"
          data-state={menu.state}
          inert={!open}
          className="mk-menu border-t border-line/70 bg-paper lg:hidden"
        >
          <div className="mk-menu__clip">
            <nav className="mx-auto flex max-w-6xl flex-col px-4 py-2 text-base">
              {navLinks.filter(([path]) => !pending(path)).map(([path, key], index) => (
                <a
                  key={path}
                  href={navHref(path)}
                  onClick={() => setOpen(false)}
                  aria-current={isCurrentMarketingLink(pathname, path) ? "page" : undefined}
                  style={menuItemStyle(index)}
                  className="mk-menu__item rounded-control px-2 py-3 text-ink hover:bg-surface aria-[current=page]:font-semibold aria-[current=page]:text-accent"
                >
                  {t(key)}
                </a>
              ))}
              <div className="my-2 border-t border-line/70" />
              <div className="mk-menu__item grid" style={menuItemStyle(navLinks.length)}>
                {trial("rounded-control border border-line bg-surface px-4 py-3 text-center font-medium text-ink hover:border-accent")}
              </div>
              <div className="mk-menu__item mt-2 flex items-center justify-between px-1 pb-2" style={menuItemStyle(navLinks.length + 1)}>
                <LangToggle />
                <ThemeToggle />
              </div>
            </nav>
          </div>
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
              <LogoMark size={32} decorative />
              <Wordmark tone="inverse" />
            </div>
            <p className="mt-2 text-sm text-paper/60">{t("landing.footerTagline")}</p>
          </div>
          <div className="flex flex-wrap gap-x-12 gap-y-8">
            <div>
              <div className="text-sm font-semibold text-paper/90">
                {t("landing.footerSolutions")}
              </div>
              <ul className="mt-3 space-y-2 text-sm text-paper/60">
                {SOLUTION_TITLES.map((item) => (
                  <li key={item.slug}><Link href={href(`/solutions/${item.slug}`)} className="hover:text-paper">{item[contentLanguage]}</Link></li>
                ))}
              </ul>
            </div>
            <div>
              <div className="text-sm font-semibold text-paper/90">
                {t("landing.footerLearn")}
              </div>
              <ul className="mt-3 space-y-2 text-sm text-paper/60">
                {GUIDE_TITLES.map((item) => (
                  <li key={item.slug}><Link href={href(`/guides/${item.slug}`)} className="hover:text-paper">{item[contentLanguage]}</Link></li>
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
                <li><Link href="/login" prefetch={false} className="hover:text-paper">{t("common.signIn")}</Link></li>
              </ul>
            </div>
            <div>
              <div className="text-sm font-semibold text-paper/90">
                {t("landing.footerCompany")}
              </div>
              <ul className="mt-3 space-y-2 text-sm text-paper/60">
                <li><Link href={href("/#contact")} className="hover:text-paper">{t("landing.navContact")}</Link></li>
                <li><Link href={href("/track")} className="hover:text-paper">{t("track.title")}</Link></li>
              </ul>
              <SiteContactLines className="mt-3 space-y-2 text-sm text-paper/60" />
            </div>
          </div>
        </div>
        <div className="mt-10 border-t border-white/10 pt-6 text-sm text-paper/70">
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
    <SiteContactProvider>
      <div className="min-h-screen bg-paper text-ink">
        <MarketingHeader />
        <main id="content" tabIndex={-1} className="focus:outline-none">{children}</main>
        <MarketingFooter />
        <WhatsAppFloat />
      </div>
    </SiteContactProvider>
  );
}
