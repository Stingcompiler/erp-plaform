"use client";

import { useEffect, useMemo, useState } from "react";
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
  X,
} from "lucide-react";

import { storageKey } from "@/lib/localIdentity";
import { countLeaves, visibleNav, SHOP_OPTIONAL } from "./nav";
import SetupPrompt from "./SetupPrompt";
import SyncStatus from "./sync/SyncStatus";
import { useAuth } from "../app/providers/AuthProvider";
import { useI18n } from "../app/providers/I18nProvider";
import { translateRole } from "@/lib/i18n";
import VezanoMark from "@/components/brand/VezanoMark";

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

  return (
    <Link
      href={item.href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      className={`relative flex items-center gap-3 rounded-control py-2.5 text-sm transition-colors ${
        nested ? "ps-9 pe-3" : "px-3"
      } ${
        active
          ? "bg-accent/20 font-semibold text-sidebarText ring-1 ring-inset ring-white/10"
          : "text-sidebarText/70 hover:bg-white/5 hover:text-sidebarText"
      }`}
    >
      {active && (
        <span className="absolute inset-y-1 start-0 w-1 rounded-full bg-accent" />
      )}
      <Icon size={18} strokeWidth={2} className="shrink-0" />
      {t(item.labelKey)}
    </Link>
  );
}

function NavGroup({ group, open, onToggle, onNavigate }) {
  const { t } = useI18n();
  const pathname = usePathname();
  const Icon = group.icon;
  // A collapsed group still has to show that the current page lives inside it.
  const holdsActive = group.children.some((c) => isActiveHref(pathname, c.href));

  return (
    <div>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className={`flex w-full items-center gap-3 rounded-control px-3 py-2.5 text-sm transition-colors ${
          holdsActive && !open
            ? "text-sidebarText"
            : "text-sidebarText/70 hover:bg-white/5 hover:text-sidebarText"
        }`}
      >
        <Icon size={18} strokeWidth={2} className="shrink-0" />
        <span className="flex-1 text-start">{t(group.labelKey)}</span>
        {holdsActive && !open && (
          <span className="h-1.5 w-1.5 rounded-full bg-accent" />
        )}
        {/* Rotation rather than a left/right chevron, so the affordance reads
            the same in RTL without mirroring the icon. */}
        <ChevronDown
          size={15}
          className={`shrink-0 transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open && (
        <div className="mt-0.5 space-y-0.5">
          {group.children.map((child) => (
            <NavLeaf
              key={child.href}
              item={child}
              onNavigate={onNavigate}
              nested
            />
          ))}
        </div>
      )}
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

  return (
    <nav className="flex-1 space-y-1 overflow-y-auto px-3 pb-4">
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
    () => visibleNav(canRead, canWrite, user?.role_name, user?.business_type, optional),
    [canRead, canWrite, user?.role_name, user?.business_type, optional],
  );
  const all = visibleNav(canRead, canWrite, user?.role_name, "enterprise").flatMap((item) => item.children || [item]);
  const toggleSection = (key) => {
    const next = optional.includes(key) ? optional.filter((k) => k !== key) : [...optional,key];
    setOptional(next);
    try { localStorage.setItem(storageKey("shopSections"), JSON.stringify(next)); } catch { /* usable for this session */ }
  };
  return (
    <>
      <div className="flex items-center gap-2.5 px-5 pt-6 font-display text-xl font-bold tracking-tight text-sidebarText">
        <span className="grid h-8 w-8 place-items-center rounded-lg bg-accent text-white"><VezanoMark size={20} /></span>
        <span>{t("common.appName")}</span>
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
      {/* Shop mode hides seven pages. Without a marker their absence looks
          like a fault rather than a setting, and there is no trail back to the
          switch that caused it. */}
      {user?.business_type === "shop" && (
        <Link
          href="/settings"
          onClick={onNavigate}
          className="mx-3 mb-1 flex items-center gap-2 rounded-control bg-white/5 px-3 py-2 text-xs text-sidebarText/70 hover:bg-white/10 hover:text-sidebarText"
        >
          <Store size={14} className="shrink-0" />
          <span className="min-w-0 flex-1 truncate">{t("shell.shopMode")}</span>
          <span className="text-sidebarText/40">{t("shell.change")}</span>
        </Link>
      )}
      <div className="p-3 text-xs text-sidebarText/40">
        v1 · {countLeaves(items)} {t("shell.sections")}
      </div>
    </>
  );
}

function Topbar({ onOpenMenu }) {
  const { user, logout } = useAuth();
  const { t, language, toggleLanguage, theme, cycleTheme } = useI18n();

  const ThemeIcon = theme === "dark" ? MoonStar : theme === "light" ? Sun : SunMoon;

  return (
    <header className="sticky top-0 z-20 flex h-16 items-center justify-between gap-2 border-b border-line/80 bg-surface/95 px-3 backdrop-blur-md sm:px-8">
      <div className="flex min-w-0 items-center gap-2">
        <button
          onClick={onOpenMenu}
          aria-label={t("shell.menu")}
          className="grid h-10 w-10 place-items-center rounded-control text-muted hover:bg-paper hover:text-ink lg:hidden"
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
          className="flex h-10 items-center gap-1.5 rounded-control px-2.5 text-sm text-muted hover:bg-paper hover:text-ink"
        >
          <Languages size={16} />
          {language === "ar" ? "العربية" : "EN"}
        </button>
        <button
          onClick={cycleTheme}
          title={`${t("shell.theme")}: ${theme}`}
          aria-label={t("shell.theme")}
          className="grid h-10 w-10 place-items-center rounded-control text-muted hover:bg-paper hover:text-ink"
        >
          <ThemeIcon size={16} />
        </button>
        <button
          onClick={logout}
          aria-label={t("common.signOut")}
          className="flex h-10 items-center gap-1.5 rounded-control px-2.5 text-sm text-muted hover:bg-paper hover:text-danger"
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
  const { user, refresh } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const [answered, setAnswered] = useState(false);
  const pathname = usePathname();

  // Close the mobile drawer on route change.
  useEffect(() => {
    setMenuOpen(false);
  }, [pathname]);

  // Asked once, and only of someone who can actually answer it: a cashier
  // shouldn't be blocked by a question that isn't theirs to settle.
  const askSetup =
    !answered &&
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

      {/* Mobile drawer */}
      {menuOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div
            className="absolute inset-0 bg-black/50"
            onClick={() => setMenuOpen(false)}
          />
          <aside className="absolute inset-y-0 start-0 flex w-72 max-w-[85%] flex-col bg-sidebar shadow-xl">
            <button
              onClick={() => setMenuOpen(false)}
              aria-label={t("common.close")}
              className="absolute end-3 top-4 grid h-9 w-9 place-items-center rounded-control text-sidebarText/70 hover:bg-white/10"
            >
              <X size={18} />
            </button>
            <SidebarContent onNavigate={() => setMenuOpen(false)} />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar onOpenMenu={() => setMenuOpen(true)} />
        <main className="workspace-main flex-1 p-4 sm:p-6 lg:p-8">{children}</main>
      </div>
    </div>
  );
}
