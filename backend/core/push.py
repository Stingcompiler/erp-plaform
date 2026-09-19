"""Web Push to a person's browsers — the one place that talks to push
services.

Best effort like email: a missing VAPID key, a dead endpoint or a push
service outage never fails the caller. A 404/410 means the browser has
forgotten the subscription; the row is deleted so we stop knocking.
"""

import json
import logging

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

GONE = {404, 410}


def push_is_enabled():
    return bool(getattr(settings, "WEB_PUSH_ENABLED", False))


def send_to_user(user, *, title, body, url="", tag=""):
    """Send one notification to every browser this person subscribed with.
    Returns how many were delivered to a push service."""
    if not push_is_enabled():
        return 0
    from pywebpush import WebPushException, webpush

    from website.models import PushSubscription

    payload = json.dumps({"title": title, "body": body, "url": url, "tag": tag})
    delivered = 0
    for sub in PushSubscription.objects.filter(user=user):
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=payload,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": settings.VAPID_CLAIMS_EMAIL},
                ttl=60 * 60 * 6,
                timeout=10,
            )
        except WebPushException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in GONE:
                sub.delete()
                continue
            sub.failures += 1
            sub.save(update_fields=["failures"])
            logger.warning("push failed for %s: %s", sub, exc)
            continue
        except Exception:  # noqa: BLE001 - never break the caller
            logger.exception("push failed for %s", sub)
            continue
        delivered += 1
        sub.last_used_at = timezone.now()
        sub.failures = 0
        sub.save(update_fields=["last_used_at", "failures"])
    return delivered
