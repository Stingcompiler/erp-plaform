"""The one place the backend sends email.

Email here is a best-effort side channel, never the system of record: every
flow that emails a link also hands the same link to the operator in the API
response, so a missing SMTP server or a bounced address can slow nobody
down. That is why ``send_transactional`` returns a boolean instead of
raising — callers report "email sent" or "deliver it yourself", and an SMTP
outage during provisioning must not roll back the provisioning.

Configuration lives in settings (EMAIL_HOST & friends); with no EMAIL_HOST
the backend is the console echo in DEBUG and a dummy sink in production,
and this module reports the send as not-sent without touching the backend.
"""

import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def email_is_enabled():
    return bool(getattr(settings, "EMAIL_ENABLED", False))


def send_transactional(subject, body, recipient):
    """Send one plain-text email; True if handed to the backend, else False.

    Failures are logged, never raised: the caller always has a manual path
    for the same information.
    """
    if not recipient:
        return False
    if not email_is_enabled():
        logger.info("Email disabled; not sending %r to %s", subject, recipient)
        return False
    try:
        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [recipient],
            fail_silently=False,
        )
    except Exception:  # noqa: BLE001 - email must never break the caller
        logger.exception("Failed to send %r to %s", subject, recipient)
        return False
    return True


def activation_link(token, *, kind=None):
    """Absolute activation URL, or None when no public origin is configured
    (a standalone install that has not set PUBLIC_APP_ORIGIN)."""
    origin = (getattr(settings, "PUBLIC_APP_ORIGIN", "") or "").rstrip("/")
    if not origin:
        return None
    from urllib.parse import urlencode

    params = {"token": token}
    if kind:
        params = {"kind": kind, **params}
    return f"{origin}/activate-owner/?{urlencode(params)}"
