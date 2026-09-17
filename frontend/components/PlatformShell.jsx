"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";
import { ChartColumn, CreditCard, FileCheck2, Inbox, Languages, LayoutDashboard, LogOut, MoonStar, ScrollText, SearchCheck, SlidersHorizontal, Sun, SunMoon, UsersRound } from "lucide-react";

import VezanoMark from "@/components/brand/VezanoMark";
import AttentionBadge, { badgeFor } from "@/components/attention/AttentionBadge";
import { useAttention } from "@/components/attention/AttentionProvider";
import { useAuth } from "@/app/providers/AuthProvider";
import { useI18n } from "@/app/providers/I18nProvider";

// Each area names the view capability a member needs (core/platform_roles.py);
// the overview has none and is open to every member. The API refuses reads
// without it, so hiding the entry here only spares the member a 403.
const PLATFORM_NAV = [
  { href: "/platform", label: "nav.platform", icon: LayoutDashboard },
  { href: "/platform-registrations", label: "nav.platformRegistrations", icon: FileCheck2, attentionKey: "platform-registrations", capability: "platform.registrations.view" },
  { href: "/platform-plans", label: "nav.platformPlans", icon: SlidersHorizontal, capability: "platform.plans.view" },
  { href: "/platform-leads", label: "nav.platformLeads", icon: Inbox, attentionKey: "platform-leads", capability: "platform.leads.view" },
  { href: "/platform-subscriptions", label: "nav.platformSubscriptions", icon: CreditCard, attentionKey: "platform-subscriptions", capability: "platform.subscriptions.view" },
  { href: "/platform-analytics", label: "nav.platformAnalytics", icon: ChartColumn, capability: "platform.seo.view" },
  { href: "/platform-seo", label: "nav.platformSeo", icon: SearchCheck, capability: "platform.seo.view" },
  { href: "/platform-team", label: "nav.platformTeam", icon: UsersRound, capability: "platform.team.view" },
  { href: "/platform-activity", label: "nav.platformActivity", icon: ScrollText, capability: "platform.team.view" },
];

export function isPlatformPath(pathname) {
  return PLATFORM_NAV.some(({ href }) => pathname === href || pathname.startsWith(`${href}/`));
}

// The member's own role ("Marketing Manager"), so nobody reads the generic
// "platform operator" label as "administrator". A Django superuser has no
// platform role and keeps the generic label.
export function usePlatformRoleLabel() {
  const { user } = useAuth();
  const { t } = useI18n();
  const roleKey = user?.role_name ? `platformTeam.roles.${user.role_name}` : null;
  const translated = roleKey ? t(roleKey) : "";
  return translated && !translated.startsWith("platformTeam.") ? translated : t("shell.platformOperator");
}

// The nav entries this member may open.
export function visiblePlatformNav(can) {
  return PLATFORM_NAV.filter(({ capability }) => !capability || can(capability));
}

export default function PlatformShell({ children }) {
  const pathname = usePathname();
  const { user, logout, can } = useAuth();
  const { t, language, toggleLanguage, theme, cycleTheme } = useI18n();
  const { counts, tones, markSeen } = useAttention();
  const roleLabel = usePlatformRoleLabel();
  const ThemeIcon = theme === "dark" ? MoonStar : theme === "light" ? Sun : SunMoon;
  // On a phone the nav is a scrolling strip; bring the current area into
  // view so the member never lands on a page whose tab is off-screen.
  const navRef = useRef(null);
  useEffect(() => {
    navRef.current?.querySelector('[aria-current="page"]')?.scrollIntoView({ block: "nearest", inline: "center" });
  }, [pathname]);

  return (
    <div className="min-h-screen bg-paper">
      <header className="border-b border-white/10 bg-sidebar text-sidebarText">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between gap-4">
            <Link href="/platform" className="flex min-w-0 items-center gap-3">
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-accent text-white">
                <VezanoMark size={24} />
              </span>
              <span className="min-w-0">
                <span className="block font-display text-lg font-bold">{t("common.appName")}</span>
                <span className="block truncate text-xs text-sidebarText/60">{t("shell.platformWorkspace")}</span>
              </span>
            </Link>
            <div className="flex items-center gap-1">
              <span className="me-2 hidden text-end sm:block">
                <span className="block text-sm font-medium">{roleLabel}</span>
                <span className="block text-xs text-sidebarText/55">{user?.email}</span>
              </span>
              <button onClick={toggleLanguage} title={t("shell.switchLanguage")} className="flex h-10 items-center gap-1.5 rounded-control px-2.5 text-sm text-sidebarText/75 hover:bg-white/10 hover:text-sidebarText">
                <Languages size={16} />{language === "ar" ? "العربية" : "EN"}
              </button>
              <button onClick={cycleTheme} title={t("shell.theme")} className="grid h-10 w-10 place-items-center rounded-control text-sidebarText/75 hover:bg-white/10 hover:text-sidebarText">
                <ThemeIcon size={16} />
              </button>
              <button onClick={logout} title={t("common.signOut")} className="grid h-10 w-10 place-items-center rounded-control text-sidebarText/75 hover:bg-white/10 hover:text-danger">
                <LogOut size={16} />
              </button>
            </div>
          </div>
          <nav ref={navRef} className="platform-nav -mx-4 flex gap-2 overflow-x-auto px-4 sm:mx-0 sm:px-0" aria-label={t("shell.platformWorkspace")}>
            {visiblePlatformNav(can).map(({ href, label, icon: Icon, attentionKey }) => {
              const active = pathname === href || pathname.startsWith(`${href}/`);
              const badge = badgeFor(attentionKey, counts, tones);
              return (
                <Link key={href} href={href} onClick={() => attentionKey && markSeen(attentionKey)} aria-current={active ? "page" : undefined} className={`flex shrink-0 items-center gap-2 rounded-control px-3 py-2 text-sm transition-colors ${active ? "bg-white text-sidebar" : "text-sidebarText/70 hover:bg-white/10 hover:text-sidebarText"}`}>
                  <Icon size={17} />{t(label)}
                  <AttentionBadge count={badge.count} tone={badge.tone} />
                </Link>
              );
            })}
          </nav>
        </div>
      </header>
      <main className="workspace-main mx-auto max-w-7xl p-4 sm:p-6 lg:p-8">{children}</main>
    </div>
  );
}
