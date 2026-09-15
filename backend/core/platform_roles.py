"""Functional split of the Vezano platform team.

Every platform member (company-less user with a platform-scoped role, or a
Django superuser) can *read* every platform screen. Writes are gated by the
capabilities below, so a collections reviewer cannot provision companies and
a support agent cannot approve money. ``Super Administrator`` keeps
everything, including managing the team and the price list.
"""

from accounts.models import Role

TEAM_MANAGE = "platform.team.manage"
PLANS_MANAGE = "platform.plans.manage"
REGISTRATIONS_REVIEW = "platform.registrations.review"
REGISTRATIONS_PROVISION = "platform.registrations.provision"
SUBSCRIPTIONS_MANAGE = "platform.subscriptions.manage"
BILLING_REVIEW = "platform.billing.review"
LEADS_MANAGE = "platform.leads.manage"
INVITATIONS_REISSUE = "platform.invitations.reissue"

ALL_CAPABILITIES = frozenset(
    {
        TEAM_MANAGE,
        PLANS_MANAGE,
        REGISTRATIONS_REVIEW,
        REGISTRATIONS_PROVISION,
        SUBSCRIPTIONS_MANAGE,
        BILLING_REVIEW,
        LEADS_MANAGE,
        INVITATIONS_REISSUE,
    }
)

# Name -> (description, capabilities). Order is the order shown to admins.
PLATFORM_ROLES = {
    "Super Administrator": (
        "Platform owner; every capability including the team and price list.",
        ALL_CAPABILITIES,
    ),
    "Subscription Manager": (
        "Runs the commercial pipeline: registrations, provisioning, "
        "subscriptions, invoices and payment review.",
        frozenset(
            {
                REGISTRATIONS_REVIEW,
                REGISTRATIONS_PROVISION,
                SUBSCRIPTIONS_MANAGE,
                BILLING_REVIEW,
                LEADS_MANAGE,
                INVITATIONS_REISSUE,
            }
        ),
    ),
    "Billing Reviewer": (
        "Collections: verifies or rejects payments and issues renewal invoices.",
        frozenset({BILLING_REVIEW}),
    ),
    "Marketing Manager": (
        "Owns the top of the funnel: works the demo requests and leads that "
        "arrive from the public site; reads everything else.",
        frozenset({LEADS_MANAGE}),
    ),
    "Support Agent": (
        "Read-only across the platform; answers demo requests and resends "
        "owner activation links.",
        frozenset({LEADS_MANAGE, INVITATIONS_REISSUE}),
    ),
}


def platform_capabilities_for(user):
    """Capabilities of a platform member; empty for tenant users."""
    if user is None or not user.is_authenticated:
        return frozenset()
    if user.is_superuser:
        return ALL_CAPABILITIES
    if not getattr(user, "is_platform_admin", False):
        return frozenset()
    role_name = user.role.name if user.role_id else None
    return PLATFORM_ROLES.get(role_name, (None, frozenset()))[1]


def user_has_platform_capability(user, capability):
    return capability in platform_capabilities_for(user)


def platform_role_choices():
    return [
        (name, description, sorted(capabilities))
        for name, (description, capabilities) in PLATFORM_ROLES.items()
    ]


def platform_role_names():
    return set(PLATFORM_ROLES)


def ensure_platform_roles():
    """Idempotently create the Role rows; used by seed_roles and invitations."""
    roles = {}
    for name in PLATFORM_ROLES:
        role, _ = Role.objects.get_or_create(
            name=name, defaults={"scope_level": Role.SCOPE_PLATFORM}
        )
        roles[name] = role
    return roles
