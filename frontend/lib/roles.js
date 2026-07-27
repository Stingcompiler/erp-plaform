/**
 * Role presentation helpers.
 *
 * The role set is deliberately not consolidated: pairs that look redundant
 * (Business Owner / Super Administrator, Finance Department / CFO) differ in
 * data scope or approval authority, and collapsing them would remove a control
 * rather than simplify one. What actually made the list hard to use was showing
 * thirteen roles as one flat dropdown, so they are grouped by family here and
 * each carries a plain-language line describing what the person can do.
 *
 * Families are presentation only — permissions live in the backend's
 * ROLE_MODULE_MATRIX and are never derived from this file.
 */

export const ROLE_FAMILIES = [
  {
    key: "leadership",
    roles: [
      "Super Administrator",
      "Business Owner",
      "General Manager",
      "Branch Manager",
    ],
  },
  {
    key: "finance",
    roles: ["Chief Financial Officer", "Finance Department"],
  },
  {
    key: "operations",
    roles: [
      "Sales Officer",
      "Purchasing Officer",
      "Inventory Officer",
      "CRM Officer",
    ],
  },
  {
    key: "support",
    roles: ["HR Officer", "Landing Page Manager"],
  },
  {
    key: "readOnly",
    roles: ["Viewer"],
  },
];

/** i18n key for a role's one-line description, or null if it has none. */
export const ROLE_HINT_KEY = {
  "Super Administrator": "superAdministrator",
  "Business Owner": "businessOwner",
  "General Manager": "generalManager",
  "Branch Manager": "branchManager",
  "Chief Financial Officer": "chiefFinancialOfficer",
  "Finance Department": "financeDepartment",
  "Sales Officer": "salesOfficer",
  "Purchasing Officer": "purchasingOfficer",
  "Inventory Officer": "inventoryOfficer",
  "CRM Officer": "crmOfficer",
  "HR Officer": "hrOfficer",
  "Landing Page Manager": "landingPageManager",
  Viewer: "viewer",
};

export function roleHint(roleName, t) {
  const key = ROLE_HINT_KEY[roleName];
  return key ? t(`users.roleHints.${key}`) : "";
}

/**
 * Buckets the server's role list into families, preserving the family order
 * above. Any role not listed — a future or custom one — falls into a trailing
 * "other" group rather than vanishing from the picker.
 */
export function groupRoles(roles) {
  const remaining = new Map(roles.map((r) => [r.name, r]));
  const groups = [];

  for (const family of ROLE_FAMILIES) {
    const members = [];
    for (const name of family.roles) {
      if (remaining.has(name)) {
        members.push(remaining.get(name));
        remaining.delete(name);
      }
    }
    if (members.length) groups.push({ key: family.key, roles: members });
  }

  if (remaining.size) {
    groups.push({ key: "other", roles: [...remaining.values()] });
  }
  return groups;
}
