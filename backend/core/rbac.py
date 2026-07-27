"""
Role-based module access (M6).

Enforcement is intentionally centralized here rather than sprinkled across
viewsets: `RoleModuleAccess` resolves the "module" for a request (from an
explicit `rbac_module` attribute, else the queryset model's app label) and
checks it against ROLE_MODULE_MATRIX. Adding it to DEFAULT_PERMISSION_CLASSES
makes every DRF endpoint from M1–M5 role-gated at once.

Access levels: "write" (implies read), "read", "none".
Platform admins (Super Administrators) bypass entirely — they already bypass
company scoping. Roles not named in the matrix fall back to a sensible default
by scope level, so an ad-hoc role can't accidentally lock a user out.
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission

WRITE = "write"
READ = "read"
NONE = "none"

MODULES = [
    "users", "org", "inventory", "sales", "purchasing",
    "sales_returns", "purchase_returns",
    "reports", "hr", "crm", "finance", "website", "settings",
]

# Map Django app labels to modules so the permission can infer the module from
# a viewset's queryset without per-view configuration.
#
# `returns` is deliberately absent: that one app holds both sides of the
# business — customer returns and credit notes on one side, supplier returns
# and debit notes on the other — and they carry different authority. A single
# app-label mapping cannot tell them apart, so every viewset in that app must
# declare `rbac_module` explicitly. `test_rbac_module_declared` enforces this;
# without it a forgotten viewset would resolve to no module at all and skip the
# role gate entirely.
APP_MODULE = {
    "accounts": "users",
    "org": "org",
    "inventory": "inventory",
    "sales": "sales",
    "purchasing": "purchasing",
    "crm": "crm",
    "hr": "hr",
    "finance": "finance",
    "website": "website",
}


def _all(level):
    return {m: level for m in MODULES}


ROLE_MODULE_MATRIX = {
    "Super Administrator": _all(WRITE),
    "Business Owner": _all(WRITE),
    "General Manager": {
        **_all(READ),
        "inventory": WRITE, "sales": WRITE, "purchasing": WRITE,
        "sales_returns": WRITE, "purchase_returns": WRITE,
        "crm": WRITE, "website": WRITE, "reports": WRITE,
        "hr": WRITE, "finance": WRITE,
    },
    "Branch Manager": {
        **_all(NONE),
        "inventory": WRITE, "sales": WRITE, "purchasing": WRITE,
        "sales_returns": WRITE, "purchase_returns": WRITE,
        "crm": WRITE, "reports": READ, "hr": READ,
    },
    "Inventory Officer": {
        **_all(NONE),
        "inventory": WRITE, "purchasing": READ, "reports": READ,
        "sales_returns": READ, "purchase_returns": READ,
    },
    # Returns are split by which side of the business they belong to. A sales
    # officer handles what customers bring back; a purchasing officer handles
    # what we send back to suppliers. Neither should be able to disposition the
    # other's returns — dispositioning is what puts goods back into sellable
    # stock, and the person who owns that decision is the one who owns the
    # original transaction.
    "Sales Officer": {
        **_all(NONE),
        "sales": WRITE, "sales_returns": WRITE, "inventory": READ, "crm": READ,
        "reports": READ,
    },
    "Purchasing Officer": {
        **_all(NONE),
        "purchasing": WRITE, "purchase_returns": WRITE, "inventory": READ,
        "reports": READ,
    },
    "HR Officer": {**_all(NONE), "hr": WRITE, "reports": READ},
    "CRM Officer": {**_all(NONE), "crm": WRITE, "sales": READ, "reports": READ},
    # Operational finance: records expenses and moves money day to day.
    "Finance Department": {
        **_all(NONE),
        "finance": WRITE, "sales": READ, "reports": READ,
    },
    # Controlling finance. Deliberately separate from "Finance Department" so
    # the person who records money is not the one who approves it (segregation
    # of duties). Gets full reporting plus purchasing/HR visibility a CFO needs.
    "Chief Financial Officer": {
        **_all(NONE),
        "finance": WRITE, "reports": WRITE,
        "sales": READ, "purchasing": READ, "hr": READ, "org": READ,
    },
    "Landing Page Manager": {**_all(NONE), "website": WRITE},
    "Viewer": {
        **_all(NONE),
        "inventory": READ, "sales": READ, "purchasing": READ,
        "sales_returns": READ, "purchase_returns": READ,
        "reports": READ, "crm": READ,
    },
}

# Fallback for roles not explicitly listed above, by scope level.
_BRANCH_FALLBACK_WRITE = {
    "inventory", "sales", "purchasing", "sales_returns", "purchase_returns",
    "crm",
}


def _fallback_level(role, module):
    scope = getattr(role, "scope_level", None)
    if scope == "platform":
        return WRITE
    if scope == "business":
        return WRITE  # business-wide roles get broad write
    if scope == "branch":
        if module in _BRANCH_FALLBACK_WRITE:
            return WRITE
        if module in ("reports", "users"):
            return READ
        return NONE
    return NONE


def level_for(role, module):
    if role is None:
        return READ  # a user with no role gets read-only
    entry = ROLE_MODULE_MATRIX.get(role.name)
    if entry is not None:
        return entry.get(module, NONE)
    return _fallback_level(role, module)


def role_can(user, module, write):
    if getattr(user, "is_platform_admin", False):
        return True
    level = level_for(getattr(user, "role", None), module)
    if level == WRITE:
        return True
    if level == READ:
        return not write
    return False


def access_map(user):
    """The {module: level} map for a user — used to build the UI's navigation."""
    if getattr(user, "is_platform_admin", False):
        return _all(WRITE)
    return {m: level_for(getattr(user, "role", None), m) for m in MODULES}


# Roles carrying financial approval authority. A payment above the company's
# approval threshold needs one of these to sign it off — recording money and
# authorising it stay separate responsibilities.
APPROVER_ROLES = {
    "Chief Financial Officer",
    "Business Owner",
    "General Manager",
    "Super Administrator",
}


def can_approve_high_value(user):
    """True when this user may approve payments above the company threshold."""
    if getattr(user, "is_platform_admin", False):
        return True
    role = getattr(user, "role", None)
    return bool(role and role.name in APPROVER_ROLES)


# Roles permitted to hard-delete a record. Module *write* access is deliberately
# not enough: an officer may create and correct their own work, but removing a
# row outright is a supervisory act. Branch Manager is included because tier-C
# deletions (a mistyped attendance row) are day-to-day branch work.
# Tier-A financial documents stay undeletable even for these roles.
DELETE_ROLES = APPROVER_ROLES | {"Branch Manager"}


def can_delete(user):
    """True when this user's role may hard-delete a record."""
    if getattr(user, "is_platform_admin", False):
        return True
    role = getattr(user, "role", None)
    return bool(role and role.name in DELETE_ROLES)


# Roles that may read the audit trail. Reading the log is an *oversight*
# function, which is not the same thing as being allowed to change settings —
# tying it to `settings: write` shut out the General Manager, the person most
# responsible for what happens day to day. Kept as an explicit list rather than
# widened to `settings: read`, because that would also hand the log to any
# future role given read access to configuration.
AUDIT_VIEWER_ROLES = {
    "Super Administrator",
    "Business Owner",
    "General Manager",
}


def can_view_audit_log(user):
    if getattr(user, "is_platform_admin", False):
        return True
    role = getattr(user, "role", None)
    if role and role.name in AUDIT_VIEWER_ROLES:
        return True
    # Anyone who can reshape company settings can already see everything the
    # log would reveal.
    return role_can(user, "settings", write=True)


class RoleModuleAccess(BasePermission):
    message = "Your role does not permit this action."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        module = self._module_for(view)
        if module is None:
            return True  # not a module-scoped endpoint; leave to other perms
        write = request.method not in SAFE_METHODS
        return role_can(user, module, write)

    def _module_for(self, view):
        explicit = getattr(view, "rbac_module", None)
        if explicit:
            return explicit
        qs = getattr(view, "queryset", None)
        if qs is not None:
            return APP_MODULE.get(qs.model._meta.app_label)
        return None
