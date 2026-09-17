"""Keep the Django admin off the tenant surface.

The admin is the one place where a signed-in staff account sees every
company's rows with no company filter and no ActivityLog entry, so it must
be (a) reachable only by the operator's superuser accounts, never by a tenant
user who happens to carry `is_staff`, (b) optionally pinned to known
addresses, and (c) audited for every write it performs.

Everything refused answers 404, indistinguishable from "no such route".
"""

from django.conf import settings
from django.http import Http404

from core.activity import get_client_ip, log_activity

ADMIN_PREFIX = "/admin/"


class AdminAccessGate:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith(ADMIN_PREFIX):
            allowed = getattr(settings, "ADMIN_ALLOWED_IPS", None) or []
            if allowed and get_client_ip(request) not in allowed:
                raise Http404
            user = getattr(request, "user", None)
            if user is not None and user.is_authenticated and not user.is_superuser:
                raise Http404
            response = self.get_response(request)
            if (
                request.method not in ("GET", "HEAD", "OPTIONS")
                and user is not None
                and user.is_authenticated
                and response.status_code < 400
            ):
                log_activity(
                    action="admin_write",
                    request=request,
                    entity_type="DjangoAdmin",
                    entity_id=request.path[len(ADMIN_PREFIX):][:64],
                    metadata={"method": request.method},
                )
            return response
        return self.get_response(request)
