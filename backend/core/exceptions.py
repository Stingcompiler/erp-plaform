"""
Project-wide DRF exception handling.

DRF maps Django's validation and permission errors to sensible responses, but
it has no mapping for `ProtectedError` / `RestrictedError`. Those are raised
when a row is deleted while `on_delete=PROTECT` relations still point at it —
which is the database correctly refusing to orphan history, not a server fault.
Left unhandled it surfaces as a 500 and an error report, and the user is told
nothing about what is actually holding the record.
"""

from django.db.models import ProtectedError, RestrictedError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


def _blocking_summary(exc):
    """Human-readable list of what still references the row, e.g.
    "4 stock movements, 1 invoice"."""
    related = (
        getattr(exc, "protected_objects", None)
        or getattr(exc, "restricted_objects", None)
        or []
    )
    counts = {}
    # Bounded: a heavily referenced row could hold thousands of objects, and
    # this runs only to build an error message.
    for obj in list(related)[:500]:
        name = obj._meta.verbose_name
        counts[name] = counts.get(name, 0) + 1
    if not counts:
        return ""
    return ", ".join(
        f"{count} {name}{'s' if count != 1 else ''}"
        for name, count in sorted(counts.items())
    )


def api_exception_handler(exc, context):
    if isinstance(exc, (ProtectedError, RestrictedError)):
        blocking = _blocking_summary(exc)
        detail = "This record is still in use and cannot be deleted."
        if blocking:
            detail = (
                f"This record is still referenced by {blocking}, "
                "so deleting it would break that history."
            )
        return Response(
            {"detail": f"{detail} Archive it instead to hide it from new work."},
            status=status.HTTP_409_CONFLICT,
        )
    return drf_exception_handler(exc, context)
