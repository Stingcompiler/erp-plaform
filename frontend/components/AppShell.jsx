"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  ChevronDown,
  Languages,
  LogOut,
  Menu,
  MoonStar,
  Store,
  Sun,
  SunMoon,
} from "lucide-react";

import { storageKey } from "@/lib/localIdentity";
import { useRouteEnter } from "@/lib/useRouteEnter";
import { useScrolledPast } from "@/lib/useScrolledPast";
import { MobileDrawer, NavIndicator, useNavIndicator } from "@/components/ui/NavMotion";
import { countLeaves, visibleNav, SHOP_OPTIONAL } from "./nav";
import AttentionBadge, { badgeFor } from "./attention/AttentionBadge";
import { useAttention } from "./attention/AttentionProvider";
import SetupPrompt from "./SetupPrompt";
import SyncStatus from "./sync/SyncStatus";
import InstallButton from "./sync/InstallButton";
import OfflineBanner from "./sync/OfflineBanner";
import StaleDataBanner from "./sync/StaleDataBanner";
import UpdateBanner from "./sync/UpdateBanner";
import AccessBanner from "./AccessBanner";
import { useSync } from "./sync/SyncProvider";
import { useConfirm } from "@/components/ui/ConfirmDialog";
import { useAuth } from "../app/providers/AuthProvider";
import { useI18n } from "../app/providers/I18nProvider";
import { translateRole } from "@/lib/i18n";
import LogoMark from "@/components/brand/LogoMark";
import Wordmark from "@/components/brand/Wordmark";

const OPEN_GROUPS_KEY = "erp.nav.openGroups";

const isActiveHref = (pathname, href) =>
  pathname === href || pathname.startsWith(href + "/");

function WorkspaceBadge({ user }) {
  const { t } = useI18n();
  const name = user?.company_name || t("shell.workspace");
  const initial = name.trim().charAt(0).toUpperCase() || "•";
  return (
    <div className="mx-3 mb-5 mt-4 flex items-center gap-3 rounded-xl border border-white/10 bg-white/5 px-3 py-3">
      <div className="grid h-9 w-9 shrink-0 place-items-center rounded-control bg-accent font-display text-sm font-semibold text-white">
        {initial}
      </div>
      <div className="min-w-0">
        <div className="truncate font-display text-sm font-semibold text-sidebarText">{name}</div>
        <div className="truncate text-xs text-sidebarText/65">
          {user?.role_name ? translateRole(user.role_name, t) : t("shell.noRole")}
        </div>
      </div>
    </div>
  );
}

function NavLeaf({ item, onNavigate, nested = false }) {
  const { t } = useI18n();
  const pathname = usePathname();
  const active = isActiveHref(pathname, item.href);
  const Icon = item.icon;
  const { counts, tones, markSeen } = useAttention();
  const badge = badgeFor(item.attentionKey, counts, tones);
  const keys = Array.isArray(item.attentionKey) ? item.attentionKey : item.attentionKey ? [item.attentionKey] : [];

  // Opening the page is the "I've seen it": the badge clears on the first
  // click and the server moves this user's since-point for those keys.
  const onClick = (event) => {
    if (!item.tabsMarkSeen) keys.forEach(markSeen);
    onNavigate?.(event);
  };

  return (
    <Link
      href={item.href}
      onClick={onClick}
      aria-current={active ? "page" : undefined}
      className={`nav-item tap relative flex items-center gap-3 rounded-control py-2.5 text-sm ${
        nested ? "ps-9 pe-3" : "px-3"
      } ${
        active
          ? "font-semibold text-sidebarText"
          : "text-sidebarText/70 hover:bg-white/5 hover:text-sidebarText"
      }`}
    >
      {/* The tint and bar of the active item until the sliding pill
          (NavIndicator) takes over. */}
      {active && <span className="nav-item__bar" />}
      <Icon size={18} strokeWidth={2} className="shrink-0" />
      <span className="flex-1 truncate">{t(item.labelKey)}</span>
      <AttentionBadge count={badge.count} tone={badge.tone} />
    </Link>
  );
}

function NavGroup({ group, open, onToggle, onNavigate }) {
  const { t } = useI18n();
  const pathname = usePathname();
  const Icon = group.icon;
  // A collapsed group still has to show that the current page lives inside it.
  const holdsActive = group.children.some((c) => isActiveHref(pathname, c.href));
  const { counts, tones } = useAttention();
  const badge = badgeFor(group.children.flatMap((c) => c.attentionKey || []), counts, tones);

  return (
    <div>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className={`nav-item tap flex w-full items-center gap-3 rounded-control px-3 py-2.5 text-sm ${
          holdsActive && !open
            ? "text-sidebarText"
            : "text-sidebarText/70 hover:bg-white/5 hover:text-sidebarText"
        }`}
      >
        <Icon size={18} strokeWidth={2} className="shrink-0" />
        <span className="flex-1 text-start">{t(group.labelKey)}</span>
        {/* Collapsed: the sum of the children's badges; expanded: each child
            carries its own, so the group stays quiet. */}
        {!open && <AttentionBadge count={badge.count} tone={badge.tone} />}
        {holdsActive && !open && !badge.count && (
          <span className="h-1.5 w-1.5 rounded-full bg-accent" />
        )}
        {/* Rotation rather than a left/right chevron, so the affordance reads
            the same in RTL without mirroring the icon. */}
        <ChevronDown
          size={15}
          className={`nav-chevron shrink-0 ${open ? "rotate-180" : ""}`}
        />
      </button>
      {/* Folds by its height (grid rows 0fr <-> 1fr); a folded group is
          inert, so its links take no focus. */}
      <div className="nav-collapse" data-open={open ? "true" : "false"}>
        <div className="nav-collapse__clip" inert={!open}>
          <div className="space-y-0.5 pt-0.5">
            {group.children.map((child) => (
              <NavLeaf
                key={child.href}
                item={child}
                onNavigate={onNavigate}
                nested
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function NavLinks({ items, onNavigate }) {
  const pathname = usePathname();
  const [openGroups, setOpenGroups] = useState(null);

  // Restore the user's last expansion state, then always force open whichever
  // group holds the current page — landing on a deep link must never leave the
  // sidebar looking like the page isn't in it.
  useEffect(() => {
    let stored = [];
    try {
      stored = JSON.parse(localStorage.getItem(OPEN_GROUPS_KEY)) || [];
    } catch {
      stored = [];
    }
    const holding = items
      .filter((i) => i.children?.some((c) => isActiveHref(pathname, c.href)))
      .map((i) => i.id);
    setOpenGroups([...new Set([...stored, ...holding])]);
    // `items` is derived from permissions and `pathname` from the route; both
    // are stable enough to key the restore on.
  }, [pathname, items]);

  const toggle = (id) => {
    setOpenGroups((prev) => {
      const next = prev.includes(id)
        ? prev.filter((g) => g !== id)
        : [...prev, id];
      try {
        localStorage.setItem(OPEN_GROUPS_KEY, JSON.stringify(next));
      } catch {
        // A browser refusing storage shouldn't break navigation.
      }
      return next;
    });
  };

  // The pill sliding to the active item; transitions arm once the saved
  // groups are open, so a page load never plays a fold.
  const { listRef, indicatorRef } = useNavIndicator(pathname, openGroups !== null);

  return (
    <nav className="flex-1 overflow-y-auto px-3 pb-4">
      <div ref={listRef} className="nav-list relative flex flex-col gap-1">
        <NavIndicator ref={indicatorRef} />
        {items.map((item) =>
          item.children ? (
            <NavGroup
              key={item.id}
              group={item}
              open={openGroups?.includes(item.id) ?? false}
              onToggle={() => toggle(item.id)}
              onNavigate={onNavigate}
            />
          ) : (
            <NavLeaf key={item.href} item={item} onNavigate={onNavigate} />
          ),
        )}
      </div>
    </nav>
  );
}

function SidebarContent({ onNavigate }) {
  const { user, canRead, canWrite } = useAuth();
  const { t } = useI18n();
  const [optional, setOptional] = useState([]);
  useEffect(() => {
    try { const saved = JSON.parse(localStorage.getItem(storageKey("shopSections")) || "[]");
      setOptional(Array.isArray(saved) ? saved : []);
    } catch { setOptional([]); }
  }, [user?.id, user?.company, user?.branch]);
  const items = useMemo(
    () => visibleNav(canRead, canWrite, user?.role_name, user?.business_type, optional, user?.is_platform_admin),
    [canRead, canWrite, user?.role_name, user?.business_type, optional, user?.is_platform_admin],
  );
  const all = visibleNav(canRead, canWrite, user?.role_name, "enterprise", [], user?.is_platform_admin).flatMap((item) => item.children || [item]);
  const toggleSection = (key) => {
    const next = optional.includes(key) ? optional.filter((k) => k !== key) : [...optional,key];
    setOptional(next);
    try { localStorage.setItem(storageKey("shopSections"), JSON.stringify(next)); } catch { /* usable for this session */ }
  };
  return (
    <>
      <div className="flex items-center gap-2.5 px-5 pt-6 font-display text-xl font-bold tracking-tight text-sidebarText">
        <LogoMark size={32} decorative />
        <Wordmark tone="dark" />
      </div>
      <WorkspaceBadge user={user} />
      <div className="mt-1 flex min-h-0 flex-1 flex-col">
        <NavLinks items={items} onNavigate={onNavigate} />
      </div>
      {user?.business_type === "shop" && <details className="mx-3 my-2 rounded-control bg-white/5 p-3 text-xs text-sidebarText/80">
        <summary className="cursor-pointer">{t("improvements.optionalPages")}</summary>
        <p className="my-2 text-sidebarText/60">{t("improvements.optionalPagesHint")}</p>
        {all.filter((item) => SHOP_OPTIONAL.includes(item.labelKey)).map((item) =>
          <label key={item.labelKey} className="flex items-center gap-2 py-1.5"><input type="checkbox" checked={optional.includes(item.labelKey)} onChange={() => toggleSection(item.labelKey)} />{t(item.labelKey)}</label>)}
      </details>}
      <InstallButton />
      {/* Shop mode hides seven pages. Without a marker their absence looks
          like a fault rather than a setting, and there is no trail back to the
          switch that caused it. */}
      {user?.business_type === "shop" && (
        <Link
          href="/settings"
          onClick={onNavigate}
          className="tap mx-3 mb-1 flex items-center gap-2 rounded-control bg-white/5 px-3 py-2 text-xs text-sidebarText/70 hover:bg-white/10 hover:text-sidebarText"
        >
          <Store size={14} className="shrink-0" />
          <span className="min-w-0 flex-1 truncate">{t("shell.shopMode")}</span>
          {/* /60, not /40: muted sidebar text at /40 measured 3.5:1. */}
          <span className="text-sidebarText/60">{t("shell.change")}</span>
        </Link>
      )}
      <div className="p-3 text-xs text-sidebarText/60">
        v1 · {countLeaves(items)} {t("shell.sections")}
      </div>
    </>
  );
}

function Topbar({ onOpenMenu }) {
  const { user, logout } = useAuth();
  const { t, language, toggleLanguage, theme, cycleTheme } = useI18n();
  const { pending, online } = useSync();
  const confirm = useConfirm();
  // Signing out with sales still waiting to upload hides them from whoever
  // signs in next, and during an outage nobody can sign back in (sign-in
  // needs the server). Say so before letting go.
  const signOut = async () => {
    // Offline with nothing waiting is still a trap: the server cannot be
    // told, the saved session is cleared, and nobody can sign in on this
    // device until the connection is back.
    if (pending > 0 || !online) {
      const message = pending > 0
        ? t(online ? "sync.signOutPending" : "sync.signOutPendingOffline", { count: pending })
        : t("sync.signOutOffline");
      if (!(await confirm(message, { tone: "danger", confirmLabel: t("common.signOut") }))) return;
    }
    logout();
  };

  const ThemeIcon = theme === "dark" ? MoonStar : theme === "light" ? Sun : SunMoon;
  // A soft shadow fades in under the bar once content scrolls beneath it.
  const scrolled = useScrolledPast();

  return (
    <header
      data-scrolled={scrolled ? "true" : "false"}
      className="shell-topbar sticky top-0 z-20 flex h-16 items-center justify-between gap-2 border-b bg-surface/95 px-3 backdrop-blur-md sm:px-8"
    >
      <div className="flex min-w-0 items-center gap-2">
        <button
          onClick={onOpenMenu}
          aria-label={t("shell.menu")}
          className="tap grid h-10 w-10 place-items-center rounded-control text-muted hover:bg-paper hover:text-ink lg:hidden"
        >
          <Menu size={20} />
        </button>
        <div className="hidden min-w-0 items-center gap-3 sm:flex">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-accent/10 text-sm font-bold text-accent" aria-hidden="true">{(user?.email || "U").charAt(0).toUpperCase()}</span>
          <div className="min-w-0"><div className="truncate text-sm font-semibold">{user?.company_name || t("shell.workspace")}</div><div className="truncate text-xs text-muted">{user?.email}</div></div>
        </div>
      </div>
      <div className="flex items-center gap-0.5 sm:gap-1">
        <SyncStatus />
        <button
          onClick={toggleLanguage}
          title={t("shell.switchLanguage")}
          className="tap flex h-10 items-center gap-1.5 rounded-control px-2.5 text-sm text-muted hover:bg-paper hover:text-ink"
        >
          <Languages size={16} />
          {language === "ar" ? "العربية" : "EN"}
        </button>
        <button
          onClick={cycleTheme}
          title={`${t("shell.theme")}: ${theme}`}
          aria-label={t("shell.theme")}
          className="tap grid h-10 w-10 place-items-center rounded-control text-muted hover:bg-paper hover:text-ink"
        >
          <ThemeIcon size={16} />
        </button>
        <button
          onClick={signOut}
          aria-label={t("common.signOut")}
          className="tap flex h-10 items-center gap-1.5 rounded-control px-2.5 text-sm text-muted hover:bg-paper hover:text-danger"
        >
          <LogOut size={16} />
          <span className="hidden sm:inline">{t("common.signOut")}</span>
        </button>
      </div>
    </header>
  );
}

export default function AppShell({ children }) {
  const { t } = useI18n();
  const { user, refresh, offlineSession } = useAuth();
  const { online } = useSync();
  const [menuOpen, setMenuOpen] = useState(false);
  const closeMenu = useCallback(() => setMenuOpen(false), []);
  const [answered, setAnswered] = useState(false);
  const pathname = usePathname();
  // The page content fades and rises in on navigation (never onto the till).
  const mainRef = useRouteEnter(pathname);

  // Close the mobile drawer on route change.
  useEffect(() => {
    setMenuOpen(false);
  }, [pathname]);

  // Asked once, and only of someone who can actually answer it: a cashier
  // shouldn't be blocked by a question that isn't theirs to settle. Never
  // while offline either — the answer needs the server, and a modal that
  // cannot be dismissed would lock the till during the very outage the
  // offline mode exists for.
  const askSetup =
    !answered &&
    !offlineSession &&
    online &&
    user?.company &&
    user?.business_type_chosen === false &&
    user?.can_manage_system_mode;

  return (
    <div className="flex min-h-screen">
      {askSetup && (
        <SetupPrompt
          onDone={() => {
            setAnswered(true);
            // Re-read identity so the navigation reshapes immediately instead
            // of waiting for the next full page load.
            refresh?.();
          }}
        />
      )}
      {/* Desktop sidebar */}
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col border-e border-white/5 bg-sidebar lg:flex">
        <SidebarContent />
      </aside>

      {/* Mobile drawer: slides in from the start edge. */}
      <MobileDrawer open={menuOpen} onClose={closeMenu} closeLabel={t("common.close")}>
        <SidebarContent onNavigate={closeMenu} />
      </MobileDrawer>

      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar onOpenMenu={() => setMenuOpen(true)} />
        <OfflineBanner />
        <StaleDataBanner />
        <UpdateBanner />
        <AccessBanner />
        <main ref={mainRef} className="workspace-main flex-1 p-4 sm:p-6 lg:p-8">{children}</main>
      </div>
    </div>
  );
}
