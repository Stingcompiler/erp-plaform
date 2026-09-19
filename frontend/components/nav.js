import {
  BarChart3,
  BookUser,
  Building2,
  ClipboardList,
  Contact,
  Globe,
  Inbox,
  LayoutDashboard,
  Package,
  RotateCcw,
  Settings,
  ShieldCheck,
  ShoppingCart,
  Truck,
  ScrollText,
  Tag,
  Users,
  UsersRound,
  Wallet,
  CreditCard,
} from "lucide-react";

// Navigation is a two-level tree: leaves link somewhere, groups carry `children`
// and never link anywhere themselves.
//
// Visibility per leaf: `module=null` is always visible; otherwise the leaf shows
// only when the user's RBAC access map grants at least read on that module.
// `requireWrite: true` narrows a leaf to write-level access — used for the audit
// log and label printing, which the server restricts to administrators, so the
// nav mirrors the API gate instead of showing a link that 403s.
//
// A group is visible only when at least one of its children is — otherwise a
// sales officer would see an empty "Administration" heading that opens to
// nothing. AppShell derives that; groups carry no module of their own.
//
// `labelKey` is a key into lib/i18n so labels translate at render time, and
// `id` is the stable key for remembering which groups the user left open.
//
// `attentionKey` names the attention source(s) (backend core/attention.py)
// whose count sits on this leaf as a badge; a group shows the sum of its
// children. Opening the leaf marks those keys seen.
export const NAV = [
  {
    labelKey: "nav.dashboard",
    href: "/dashboard",
    module: null,
    icon: LayoutDashboard,
  },
  {
    id: "sales",
    labelKey: "nav.groups.sales",
    icon: ShoppingCart,
    children: [
      { labelKey: "nav.sales", href: "/sales", module: "sales", icon: ShoppingCart, attentionKey: "sales" },
      { labelKey: "nav.debts", href: "/debts", module: "sales", icon: Wallet, attentionKey: "debts" },
      { labelKey: "nav.webOrders", href: "/web-orders", module: "sales", icon: Globe, attentionKey: "web-orders" },
      {
        labelKey: "nav.customerRecords",
        href: "/customer-records",
        module: "sales",
        icon: BookUser,
      },
      { labelKey: "nav.crm", href: "/crm", module: "crm", icon: Contact, attentionKey: "crm" },
    ],
  },
  {
    id: "purchasing",
    labelKey: "nav.groups.purchasing",
    icon: Truck,
    children: [
      {
        labelKey: "nav.purchasing",
        href: "/purchasing",
        module: "purchasing",
        icon: Truck,
      },
      {
        labelKey: "nav.supplierRecords",
        href: "/supplier-records",
        module: "purchasing",
        icon: ClipboardList,
      },
    ],
  },
  {
    id: "inventory",
    labelKey: "nav.groups.inventory",
    icon: Package,
    children: [
      {
        labelKey: "nav.inventory",
        href: "/inventory",
        module: "inventory",
        icon: Package,
        attentionKey: ["inventory", "stock"],
      },
      {
        labelKey: "nav.labels",
        href: "/labels",
        module: "inventory",
        requireWrite: true,
        icon: Tag,
      },
    ],
  },
  // Returns stays top-level rather than being duplicated under both Sales and
  // Purchasing: two links to one page break the active-item highlight. The
  // page itself carries both sides and gates its own tabs, so the link shows
  // for anyone holding either module.
  {
    labelKey: "nav.returns",
    href: "/returns",
    module: "sales_returns",
    altModule: "purchase_returns",
    icon: RotateCcw,
    attentionKey: "returns",
  },
  { labelKey: "nav.finance", href: "/finance", module: "finance", icon: Wallet, attentionKey: "finance" },
  { labelKey: "nav.hr", href: "/hr", module: "hr", icon: UsersRound, attentionKey: "hr" },
  { labelKey: "nav.reports", href: "/reports", module: "reports", icon: BarChart3 },
  {
    id: "admin",
    labelKey: "nav.groups.admin",
    icon: ShieldCheck,
    children: [
      {
        labelKey: "nav.platformLeads",
        href: "/platform-leads",
        module: null,
        platformOnly: true,
        icon: Inbox,
      },
      {
        labelKey: "nav.platformSubscriptions",
        href: "/platform-subscriptions",
        module: null,
        platformOnly: true,
        icon: CreditCard,
      },
      {
        labelKey: "nav.subscription",
        href: "/subscription",
        module: null,
        ownerOnly: true,
        icon: CreditCard,
        attentionKey: "subscription",
      },
      { labelKey: "nav.org", href: "/org", module: "org", icon: Building2 },
      { labelKey: "nav.users", href: "/users", module: "users", icon: Users },
      { labelKey: "nav.website", href: "/website", module: "website", icon: Globe },
      {
        labelKey: "nav.logs",
        href: "/logs",
        // The audit log is an oversight function, not a settings one: the
        // server (IsAuditViewer / AUDIT_VIEWER_ROLES) grants it to the owner
        // and general manager too. `auditViewer` is resolved from the role
        // rather than a module so the nav mirrors that exactly instead of
        // hiding a page the API would allow.
        auditViewer: true,
        icon: ScrollText,
      },
      {
        labelKey: "nav.settings",
        href: "/settings",
        module: "settings",
        icon: Settings,
      },
    ],
  },
];

/**
 * Prunes the tree to what this user may see: leaves are filtered by module
 * access, then groups left with no children are dropped entirely.
 */
// Roles the server lets read the audit trail — mirrors
// core.rbac.AUDIT_VIEWER_ROLES. Kept in sync by an explicit test.
export const AUDIT_VIEWER_ROLES = [
  "Super Administrator",
  "Business Owner",
  "General Manager",
];

// Pages a single shop has no use for. A corner grocery has one location, no
// leads pipeline, no staff records worth a module, and no public website — and
// showing them all is what made the app feel like enterprise software to
// someone who just wants to ring up sales.
//
// This hides pages; it does NOT remove permission. Anything here is still
// reachable by URL and still enforced by the server, so nothing about the
// security model depends on it and switching a company back to enterprise
// restores everything untouched.
export const SHOP_OPTIONAL = [
  "nav.crm",
  "nav.hr",
  "nav.website",
  "nav.org",
  "nav.customerRecords",
  "nav.supplierRecords",
  "nav.labels",
];
const SHOP_HIDDEN = new Set(SHOP_OPTIONAL);

export function visibleNav(canRead, canWrite, roleName, businessType, optional = [], isPlatformAdmin = false) {
  const shopMode = businessType === "shop";
  // `altModule` covers a page that serves two modules at once (Returns holds
  // both the sales and purchasing sides): holding either one is enough to see
  // the link, and the page gates its own tabs from there.
  const allowed = (item) => {
    if (item.platformOnly) return isPlatformAdmin;
    if (item.ownerOnly) return roleName === "Business Owner";
    if (shopMode && SHOP_HIDDEN.has(item.labelKey) && !optional.includes(item.labelKey)) return false;
    if (item.auditViewer) {
      return (
        AUDIT_VIEWER_ROLES.includes(roleName) || canWrite("settings")
      );
    }
    const check = item.requireWrite ? canWrite : canRead;
    return check(item.module) || (item.altModule ? check(item.altModule) : false);
  };

  return NAV.reduce((acc, item) => {
    if (!item.children) {
      if (allowed(item)) acc.push(item);
      return acc;
    }
    const children = item.children.filter(allowed);
    if (!children.length) return acc;
    // A group wrapping a single link is pure friction — an extra click to
    // reach one page. Common in shop mode, where most groups lose their
    // siblings, but it applies to any role whose access narrows a group down
    // to one page.
    if (children.length === 1) {
      acc.push(children[0]);
      return acc;
    }
    acc.push({ ...item, children });
    return acc;
  }, []);
}

/** Flat list of reachable pages — used for the "N sections" footer count. */
export function countLeaves(items) {
  return items.reduce(
    (total, item) => total + (item.children ? item.children.length : 1),
    0,
  );
}
