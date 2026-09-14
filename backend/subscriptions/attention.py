"""Attention source for commercial access. Unlike the others it ignores
`since`: while the company is in grace or read-only the owner's badge stays
on, however many times the page is opened — it is a state, not news."""

from core.attention import TONE_DANGER, register

WARN_STATES = {"grace", "read_only", "version_not_covered", "unlicensed", "past_due", "suspended"}


@register("subscription", "settings", TONE_DANGER)
def access_needs_renewal(user, since):
    from core.entitlements import resolve_entitlements

    company = getattr(user, "company", None)
    role = getattr(user, "role", None)
    # The Subscription & licence page is owner-only; so is its badge.
    if company is None or not role or role.name != "Business Owner":
        return 0
    decision = resolve_entitlements(company, apply_policy=False)
    return 1 if decision.state in WARN_STATES else 0
