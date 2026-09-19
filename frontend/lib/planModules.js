// The modules a plan version can include — the same codes core/rbac.py
// MODULES accepts, in the order they appear in the app's navigation, with the
// dependencies subscriptions.PlanVersion.clean() enforces so the picker can
// keep a selection valid before the server ever sees it.
export const PLAN_MODULES = [
  "inventory", "sales", "purchasing", "sales_returns", "purchase_returns",
  "crm", "hr", "finance", "reports", "website", "org", "users", "settings",
];

// Never plan-gated (core.entitlements.CORE_MODULES): running the company —
// its people, branches and settings — comes with every plan; the limits
// decide how many. Shown as included, never as a choice.
export const CORE_MODULES = ["users", "org", "settings"];

export const MODULE_DEPENDENCIES = {
  sales_returns: ["sales", "inventory"],
  purchase_returns: ["purchasing", "inventory"],
};

export const ALL_MODULES = "*";

// Toggle `code` in `selected`, pulling in what it needs and dropping what
// needed it. Returns a new array in PLAN_MODULES order.
export function toggleModule(selected, code) {
  const set = new Set(selected.filter((item) => item !== ALL_MODULES));
  if (set.has(code)) {
    set.delete(code);
    for (const [dependent, needs] of Object.entries(MODULE_DEPENDENCIES)) {
      if (needs.includes(code)) set.delete(dependent);
    }
  } else {
    set.add(code);
    for (const need of MODULE_DEPENDENCIES[code] || []) set.add(need);
  }
  return PLAN_MODULES.filter((item) => set.has(item));
}

// A module's display name in the UI language; "*" means every module.
export function moduleLabel(code, t) {
  if (code === ALL_MODULES) return t("platformPlans.allModules");
  const label = t(`platformPlans.moduleNames.${code}`);
  return label.startsWith("platformPlans.") ? code : label;
}

// The modules a version really includes, "*" expanded, in navigation order.
export function expandModules(modules) {
  const list = modules || [];
  if (list.includes(ALL_MODULES)) return [...PLAN_MODULES];
  return PLAN_MODULES.filter((code) => list.includes(code));
}

// What the API should receive: ["*"] when everything is ticked.
export function normalizeModules(selected) {
  if (selected.includes(ALL_MODULES)) return [ALL_MODULES];
  return PLAN_MODULES.filter((item) => selected.includes(item));
}
