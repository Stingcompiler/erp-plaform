"""Deployment-time configuration checks (`manage.py check`, CI, preflight).

These guard settings whose unsafe combinations would otherwise only be found
by an attacker.
"""

from django.conf import settings
from django.core.checks import Error, Tags, register


@register(Tags.security)
def cookie_samesite_requires_csrf(app_configs, **kwargs):
    """Cookie-carried JWTs are sent by the browser on every cross-site request.
    SameSite=Lax is what stops a third-party page from making state-changing
    calls with them; the API performs no CSRF token check of its own. Relaxing
    the cookie to SameSite=None therefore opens every POST to CSRF."""
    samesite = str(settings.SIMPLE_JWT.get("AUTH_COOKIE_SAMESITE") or "").lower()
    if samesite == "none":
        return [
            Error(
                "AUTH_COOKIE_SAMESITE=None disables the only CSRF protection the "
                "cookie-JWT API has.",
                hint="Serve the frontend from the API origin and keep SameSite=Lax "
                "(or Strict). Cross-origin frontends need a CSRF token scheme first.",
                id="vezano.E001",
            )
        ]
    return []
