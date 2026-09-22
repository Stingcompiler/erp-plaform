"""First-party error monitoring: unhandled exceptions land in a table the
platform console reads, instead of only in the host's process logs.

The middleware records and steps aside — it returns None so Django's own
500 handling proceeds exactly as before, and every part of the recording
is allowed to fail (an error monitor that can itself take the site down
is worse than none). A re-raised occurrence of the same error updates one
row's count rather than adding rows, so an error storm stays readable.

The stored traceback is the exception's own frames — code locations, not
request bodies — and settings are never echoed into it (Django's fancy
debug page is not involved; this is plain `traceback.format_exception`).
"""

import hashlib
import logging
import traceback as traceback_module

from django.conf import settings
from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.db import models
from django.http import Http404
from django.utils import timezone

logger = logging.getLogger(__name__)

TRACEBACK_LIMIT = 6000


def _fingerprint(exc, request):
    """One row per (error type, raising location, route)."""
    tb = exc.__traceback__
    last = traceback_module.extract_tb(tb)[-1:] if tb else []
    frame = f"{last[0].filename}:{last[0].lineno}" if last else ""
    raw = f"{type(exc).__name__}|{frame}|{request.path}"
    return hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()[:32]


# Exceptions that are the correct answer to a bad request, not a fault in the
# service: a visitor typing a store slug that does not exist, a user opening a
# page their role forbids, a malformed host header. They already produce the
# right status code, and recording them buries real errors under noise.
EXPECTED = (Http404, PermissionDenied, SuspiciousOperation)


class ErrorMonitorMiddleware:
    """Records unhandled view exceptions; DEBUG runs keep the debug page
    as the whole story and are not recorded, and so are expected 4xx
    exceptions (see EXPECTED)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        if settings.DEBUG or isinstance(exception, EXPECTED):
            return None
        try:
            from core.models import ErrorEvent

            user = getattr(request, "user", None)
            trace = "".join(
                traceback_module.format_exception(exception, limit=12)
            )[-TRACEBACK_LIMIT:]
            updated = ErrorEvent.objects.filter(
                fingerprint=_fingerprint(exception, request)
            ).update(
                count=models.F("count") + 1,
                message=str(exception)[:500],
                traceback=trace,
                resolved_at=None,
                # update() bypasses auto_now, so refresh it explicitly.
                last_seen=timezone.now(),
            )
            if not updated:
                ErrorEvent.objects.create(
                    fingerprint=_fingerprint(exception, request),
                    exc_type=type(exception).__name__[:200],
                    message=str(exception)[:500],
                    path=request.path[:300],
                    method=request.method[:8],
                    traceback=trace,
                    user_id=getattr(user, "pk", None),
                    company_id=getattr(user, "company_id", None),
                )
        except Exception:  # noqa: BLE001 - the monitor must never add a failure
            logger.exception("Could not record error event")
        return None
