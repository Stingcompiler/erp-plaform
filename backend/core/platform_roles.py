"""Functional split of the Vezano platform team.

A platform member is a company-less user with a platform-scoped role, or a
Django superuser. Each area of the console has a *view* capability and one
or more *write* capabilities; a role sees only the areas it holds a view for
and changes only what its write capabilities allow. The overview page is
open to every member. ``Super Administrator`` keeps everything, including
managing the team and the price list.

The split follows who needs what: money (subscriptions, invoices, payment
proofs) is visible to the commercial and collections roles only; the team
list is the Super Administrator's alone; marketing sees the funnel — demo
requests and registrations — and the price list it sells, nothing else.
"""

from accounts.models import Role

# View capabilities: one per console area. A write capability below implies
# the view of its area (see _with_views).
TEAM_VIEW = "platform.team.view"
PLANS_VIEW = "platform.plans.view"
REGISTRATIONS_VIEW = "platform.registrations.view"
SUBSCRIPTIONS_VIEW = "platform.subscriptions.view"
BILLING_VIEW = "platform.billing.view"
LEADS_VIEW = "platform.leads.view"
SEO_VIEW = "platform.seo.view"

# Write capabilities.
TEAM_MANAGE = "platform.team.manage"
PLANS_MANAGE = "platform.plans.manage"
REGISTRATIONS_REVIEW = "platform.registrations.review"
REGISTRATIONS_PROVISION = "platform.registrations.provision"
SUBSCRIPTIONS_MANAGE = "platform.subscriptions.manage"
BILLING_REVIEW = "platform.billing.review"
LEADS_MANAGE = "platform.leads.manage"
INVITATIONS_REISSUE = "platform.invitations.reissue"
SEO_MANAGE = "platform.seo.manage"

VIEW_OF = {
    TEAM_MANAGE: TEAM_VIEW,
    PLANS_MANAGE: PLANS_VIEW,
    REGISTRATIONS_REVIEW: REGISTRATIONS_VIEW,
    REGISTRATIONS_PROVISION: REGISTRATIONS_VIEW,
    INVITATIONS_REISSUE: REGISTRATIONS_VIEW,
    SUBSCRIPTIONS_MANAGE: SUBSCRIPTIONS_VIEW,
    BILLING_REVIEW: BILLING_VIEW,
    LEADS_MANAGE: LEADS_VIEW,
    SEO_MANAGE: SEO_VIEW,
}

VIEW_CAPABILITIES = frozenset(VIEW_OF.values())
WRITE_CAPABILITIES = frozenset(VIEW_OF)
ALL_CAPABILITIES = VIEW_CAPABILITIES | WRITE_CAPABILITIES


def _with_views(*capabilities):
    """A role's capability set: what was listed plus the view of every write."""
    listed = set(capabilities)
    return frozenset(listed | {VIEW_OF[c] for c in listed if c in VIEW_OF})


# Name -> (description, capabilities). Order is the order shown to admins.
PLATFORM_ROLES = {
    "Super Administrator": (
        "Platform owner; every capability including the team and price list.",
        ALL_CAPABILITIES,
    ),
    "Subscription Manager": (
        "Runs the commercial pipeline: registrations, provisioning, "
        "subscriptions, invoices and payment review; reads the price list; "
        "tunes the public site's search settings.",
        _with_views(
            REGISTRATIONS_REVIEW,
            REGISTRATIONS_PROVISION,
            SUBSCRIPTIONS_MANAGE,
            BILLING_REVIEW,
            LEADS_MANAGE,
            INVITATIONS_REISSUE,
            SEO_MANAGE,
            PLANS_VIEW,
        ),
    ),
    "Billing Reviewer": (
        "Collections: sees subscriptions and money, verifies or rejects "
        "payments and issues renewal invoices. Nothing else.",
        _with_views(BILLING_REVIEW, SUBSCRIPTIONS_VIEW),
    ),
    "Marketing Manager": (
        "Owns the top of the funnel: works demo requests and leads, tunes the "
        "public site's search settings, reads the registrations they produce "
        "and the price list. No money, no team.",
        _with_views(LEADS_MANAGE, SEO_MANAGE, REGISTRATIONS_VIEW, PLANS_VIEW),
    ),
    "Support Agent": (
        "Answers demo requests, resends owner activation links, and reads "
        "registrations, subscriptions and the search settings to help a "
        "customer. No money, no price list, no team.",
        _with_views(LEADS_MANAGE, INVITATIONS_REISSUE, SUBSCRIPTIONS_VIEW, SEO_VIEW),
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


def ensure_platform_roles():
    """Idempotently create the Role rows; used by seed_roles and invitations."""
    roles = {}
    for name in PLATFORM_ROLES:
        role, _ = Role.objects.get_or_create(
            name=name, defaults={"scope_level": Role.SCOPE_PLATFORM}
        )
        roles[name] = role
    return roles
