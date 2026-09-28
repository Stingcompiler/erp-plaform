"""Deployment-time configuration checks (`manage.py check`, CI, preflight).

These guard settings whose unsafe combinations would otherwise only be found
by an attacker.
"""

from django.conf import settings
from django.core.checks import Error, Tags, register


@register(Tags.security)
def cookie_samesite_requires_csrf(app_configs, **kwargs):
    """Cookie-carried JWTs are sent by the browser on every cross-site request.
    SameSite=Lax is the first thing that stops a third-party page from making
    state-changing calls with them; the CSRF token check on cookie-
    authenticated writes (accounts.authentication.enforce_csrf) is the
    second, and it only works while the csrftoken cookie itself stays
    same-site. Relaxing the auth cookie to SameSite=None gives both up."""
    samesite = str(settings.SIMPLE_JWT.get("AUTH_COOKIE_SAMESITE") or "").lower()
    if samesite == "none":
        return [
            Error(
                "AUTH_COOKIE_SAMESITE=None removes the same-site guarantee the "
                "cookie-JWT API's CSRF protection is built on.",
                hint="Serve the frontend from the API origin and keep SameSite=Lax "
                "(or Strict).",
                id="vezano.E001",
            )
        ]
    return []


@register()
def branch_policy_registry_is_consistent(app_configs, **kwargs):
    """Every company-scoped resource must carry an explicit branch policy.

    See core.branch_policy: without this check, forgetting `branch_field` on
    a new viewset silently makes the resource company-wide for branch users.
    """
    from core.branch_policy import policy_violations

    return [
        Error(message, id="vezano.E002")
        for message in policy_violations()
    ]
