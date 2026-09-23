"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { ChartColumn, CreditCard, FileCheck2, Inbox, Languages, LayoutDashboard, LogOut, MoonStar, ScrollText, SearchCheck, ShieldAlert, SlidersHorizontal, Sun, SunMoon, UsersRound, Building2, Banknote, Menu, X } from "lucide-react";

import VezanoMark from "@/components/brand/VezanoMark";
import AttentionBadge, { badgeFor } from "@/components/attention/AttentionBadge";
import { useAttention } from "@/components/attention/AttentionProvider";
import { useAuth } from "@/app/providers/AuthProvider";
import { useI18n } from "@/app/providers/I18nProvider";

// Each area names the view capability a member needs (core/platform_roles.py);
// the overview has none and is open to every member. The API refuses reads
// without it, so hiding the entry here only spares the member a 403.
//
// Areas are grouped by the desk that works them, so each role finds its day
// in one block: marketing brings people in, the subscription desk turns them
// into companies, billing looks after the money, growth watches the public
// site, and the owner of the platform oversees the team and the errors.
const PLATFORM_GROUPS = [
  {
    id: "overview",
    items: [
      { href: "/platform", label: "nav.platform", icon: LayoutDashboard },
    ],
  },
  {
    id: "acquisition",
    label: "shell.platformGroups.acquisition",
    items: [
      { href: "/platform-leads", label: "nav.platformLeads", icon: Inbox, attentionKey: "platform-leads", capability: "platform.leads.view" },
      { href: "/platform-registrations", label: "nav.platformRegistrations", icon: FileCheck2, attentionKey: "platform-registrations", capability: "platform.registrations.view" },
    ],
  },
  {
    id: "accounts",
    label: "shell.platformGroups.accounts",
    items: [
      { href: "/platform-companies", label: "nav.platformCompanies", icon: Building2, capability: "platform.subscriptions.view" },
      { href: "/platform-subscriptions", label: "nav.platformSubscriptions", icon: CreditCard, attentionKey: "platform-subscriptions", capability: "platform.subscriptions.view" },
    ],
  },
  {
    id: "revenue",
    label: "shell.platformGroups.revenue",
    items: [
      { href: "/platform-finance", label: "nav.platformFinance", icon: Banknote, capability: "platform.billing.view" },
      { href: "/platform-plans", label: "nav.platformPlans", icon: SlidersHorizontal, capability: "platform.plans.view" },
    ],
  },
  {
    id: "growth",
    label: "shell.platformGroups.growth",
    items: [
      { href: "/platform-analytics", label: "nav.platformAnalytics", icon: ChartColumn, capability: "platform.seo.view" },
      { href: "/platform-seo", label: "nav.platformSeo", icon: SearchCheck, capability: "platform.seo.view" },
    ],
  },
  {
    id: "oversight",
    label: "shell.platformGroups.oversight",
    items: [
      { href: "/platform-team", label: "nav.platformTeam", icon: UsersRound, capability: "platform.team.view" },
      { href: "/platform-activity", label: "nav.platformActivity", icon: ScrollText, capability: "platform.team.view" },
      { href: "/platform-errors", label: "nav.platformErrors", icon: ShieldAlert, attentionKey: "platform-errors", capability: "platform.team.view" },
    ],
  },
];

const PLATFORM_NAV = PLATFORM_GROUPS.flatMap((group) => group.items);

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

// The areas this member may open, grouped; a desk with nothing this member
// may open disappears.
function visiblePlatformGroups(can) {
  return PLATFORM_GROUPS.map((group) => ({
    ...group,
    items: group.items.filter(({ capability }) => !capability || can(capability)),
  })).filter((group) => group.items.length);
}

function PlatformNav({ onNavigate }) {
  const pathname = usePathname();
  const { can } = useAuth();
  const { t } = useI18n();
  const { counts, tones, markSeen } = useAttention();
  return (
    <nav className="flex-1 space-y-4 overflow-y-auto px-3 pb-4" aria-label={t("shell.platformWorkspace")}>
      {visiblePlatformGroups(can).map((group) => (
        <div key={group.id}>
          {group.label && (
            <div className="px-3 pb-1.5 text-[11px] font-semibold uppercase tracking-wider text-sidebarText/45">
              {t(group.label)}
            </div>
          )}
          <div className="space-y-0.5">
            {group.items.map(({ href, label, icon: Icon, attentionKey }) => {
              const active = pathname === href || pathname.startsWith(`${href}/`);
              const badge = badgeFor(attentionKey, counts, tones);
              return (
                <Link
                  key={href}
                  href={href}
                  onClick={() => { if (attentionKey) markSeen(attentionKey); onNavigate?.(); }}
                  aria-current={active ? "page" : undefined}
                  className={`relative flex items-center gap-3 rounded-control px-3 py-2.5 text-sm transition-colors ${
                    active
                      ? "bg-accent/20 font-semibold text-sidebarText ring-1 ring-inset ring-white/10"
                      : "text-sidebarText/70 hover:bg-white/5 hover:text-sidebarText"
                  }`}
                >
                  {active && <span className="absolute inset-y-1 start-0 w-1 rounded-full bg-accent" />}
                  <Icon size={18} strokeWidth={2} className="shrink-0" />
                  <span className="flex-1 truncate">{t(label)}</span>
                  <AttentionBadge count={badge.count} tone={badge.tone} />
                </Link>
              );
            })}
          </div>
        </div>
      ))}
    </nav>
  );
}

function PlatformSidebar({ onNavigate }) {
  const { user } = useAuth();
  const { t } = useI18n();
  const roleLabel = usePlatformRoleLabel();
  return (
    <>
      <Link href="/platform" onClick={onNavigate} className="flex items-center gap-2.5 px-5 pt-6 font-display text-xl font-bold tracking-tight text-sidebarText">
        <span className="grid h-8 w-8 place-items-center rounded-lg bg-accent text-white"><VezanoMark size={20} /></span>
        <span>{t("common.appName")}</span>
      </Link>
      <div className="mx-3 mb-5 mt-4 rounded-xl border border-white/10 bg-white/5 px-3 py-3">
        <div className="truncate font-display text-sm font-semibold text-sidebarText">{t("shell.platformWorkspace")}</div>
        <div className="truncate text-xs text-sidebarText/65">{roleLabel}</div>
        <div className="mt-0.5 truncate text-xs text-sidebarText/45" dir="ltr">{user?.email}</div>
      </div>
      <PlatformNav onNavigate={onNavigate} />
    </>
  );
}

export default function PlatformShell({ children }) {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const { t, language, toggleLanguage, theme, cycleTheme } = useI18n();
  const roleLabel = usePlatformRoleLabel();
  const ThemeIcon = theme === "dark" ? MoonStar : theme === "light" ? Sun : SunMoon;
  const [menuOpen, setMenuOpen] = useState(false);

  // A new page closes the phone drawer.
  useEffect(() => { setMenuOpen(false); }, [pathname]);

  return (
    <div className="flex min-h-screen bg-paper">
      {/* Desktop: the grouped navigation stays in view down the side. */}
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col border-e border-white/5 bg-sidebar lg:flex">
        <PlatformSidebar />
      </aside>

      {/* Phone and tablet: the same sidebar, as a drawer. */}
      {menuOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/50" onClick={() => setMenuOpen(false)} />
          <aside className="absolute inset-y-0 start-0 flex w-72 max-w-[85%] flex-col bg-sidebar shadow-xl">
            <button
              onClick={() => setMenuOpen(false)}
              aria-label={t("common.close")}
              className="absolute end-3 top-4 grid h-9 w-9 place-items-center rounded-control text-sidebarText/70 hover:bg-white/10"
            >
              <X size={18} />
            </button>
            <PlatformSidebar onNavigate={() => setMenuOpen(false)} />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-16 items-center justify-between gap-2 border-b border-line/80 bg-surface/95 px-3 backdrop-blur-md sm:px-8">
          <div className="flex min-w-0 items-center gap-2">
            <button
              onClick={() => setMenuOpen(true)}
              aria-label={t("shell.menu")}
              className="grid h-10 w-10 place-items-center rounded-control border border-line bg-surface text-ink hover:border-accent lg:hidden"
            >
              <Menu size={20} />
            </button>
            <div className="hidden min-w-0 sm:block">
              <div className="truncate text-sm font-semibold">{roleLabel}</div>
              <div className="truncate text-xs text-muted" dir="ltr">{user?.email}</div>
            </div>
          </div>
          <div className="flex items-center gap-0.5 sm:gap-1">
            <button onClick={toggleLanguage} title={t("shell.switchLanguage")} className="flex h-10 items-center gap-1.5 rounded-control px-2.5 text-sm text-muted hover:bg-paper hover:text-ink">
              <Languages size={16} />{language === "ar" ? "العربية" : "EN"}
            </button>
            <button onClick={cycleTheme} title={t("shell.theme")} aria-label={t("shell.theme")} className="grid h-10 w-10 place-items-center rounded-control text-muted hover:bg-paper hover:text-ink">
              <ThemeIcon size={16} />
            </button>
            <button onClick={logout} aria-label={t("common.signOut")} className="flex h-10 items-center gap-1.5 rounded-control px-2.5 text-sm text-muted hover:bg-paper hover:text-danger">
              <LogOut size={16} />
              <span className="hidden sm:inline">{t("common.signOut")}</span>
            </button>
          </div>
        </header>
        <main className="workspace-main min-w-0 flex-1 p-4 sm:p-6 lg:p-8">{children}</main>
      </div>
    </div>
  );
}
