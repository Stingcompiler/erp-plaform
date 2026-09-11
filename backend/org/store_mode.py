"""Access policy for the simplified shop operating mode.

The policy is derived at request time.  It never flips ``User.is_active``:
switching back to company mode immediately restores every preserved account.
"""

from django.db.models import Q


STORE_DEFAULT_ROLE_NAMES = frozenset({
    "Business Owner",
    "Sales Officer",
    "Inventory Officer",
    "Purchasing Officer",
})


def is_system_mode_owner(user):
    """Only the company's Business Owner may change operating mode."""
    role = getattr(user, "role", None)
    return bool(
        getattr(user, "company_id", None)
        and role
        and role.name == "Business Owner"
    )


def is_store_mode_allowed(user):
    """Whether a user may enter while their company operates as a shop."""
    if getattr(user, "is_platform_admin", False) or not getattr(user, "company_id", None):
        return True
    company = getattr(user, "company", None)
    if company is None or company.business_type != "shop":
        return True
    if is_system_mode_owner(user):
        return True
    role = getattr(user, "role", None)
    if role and role.name in STORE_DEFAULT_ROLE_NAMES:
        return True
    from org.models import StoreModeAccessException
    return StoreModeAccessException.objects.filter(
        company_id=user.company_id,
    ).filter(
        Q(user_id=user.id) | Q(role_id=getattr(user, "role_id", None))
    ).exists()
