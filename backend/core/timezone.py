"""Per-company business time zone.

Django resolves ``timezone.localdate()`` and ``__date`` lookups against the
*active* time zone, which is thread-local. Requests are authenticated inside
DRF (JWT in a cookie), after Django middleware has run, so the zone is
activated from the authentication class once the user is known, and the
middleware here only guarantees that nothing leaks from one request to the
next on a reused worker thread.
"""
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.utils import timezone


def is_valid_timezone(name):
    try:
        ZoneInfo(str(name))
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        return False
    return True


def activate_for_user(user):
    """Activate the user's company zone; fall back to the server default."""
    name = getattr(getattr(user, "company", None), "timezone", "") or ""
    if is_valid_timezone(name):
        timezone.activate(ZoneInfo(name))
    else:
        timezone.deactivate()


def company_zone(company):
    """The company's business zone, for work that runs outside a request
    (a posting from a management command, a backfill) where no zone has been
    activated. Falls back to the server default when it has none or a bad one."""
    name = getattr(company, "timezone", "") or ""
    if is_valid_timezone(name):
        return ZoneInfo(name)
    return timezone.get_default_timezone()


class CompanyTimezoneMiddleware:
    """Reset the active zone around every request so a worker thread never
    carries one company's zone into the next request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        timezone.deactivate()
        try:
            return self.get_response(request)
        finally:
            timezone.deactivate()
