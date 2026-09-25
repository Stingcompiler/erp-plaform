"""Hide the SaaS-only surface on a customer's own server.

A standalone installation runs the same code as the hosted platform, so the
platform inbox, plan catalogue, public registration form, demo requests and
platform-team invitations are all still routable there. None of them make
sense for a customer (there is no platform team, nobody registers), and
every one is attack surface. Rather than touch each view, one middleware
answers 404 for those prefixes when the deployment mode is standalone —
indistinguishable from "this route does not exist", which is the truth for
that installation.

`public/site/<slug>/` is deliberately NOT gated: a customer's own public
website is theirs to serve.
"""

import re

from django.http import JsonResponse
from django.utils.translation import gettext as _

from config.deployment import get_deployment_config

SAAS_ONLY = re.compile(
    r"^/api/(?:"
    r"platform/"
    r"|public/(?:demo-requests|plans|registration-requests|owner-invitations"
    r"|platform-invitations|track)/"
    r")"
)


class StandaloneSurfaceGate:
    def __init__(self, get_response):
        self.get_response = get_response
        self._standalone = None

    def _is_standalone(self):
        if self._standalone is None:
            self._standalone = get_deployment_config().is_standalone
        return self._standalone

    def __call__(self, request):
        if self._is_standalone() and SAAS_ONLY.match(request.path):
            return JsonResponse({"detail": _("Not found.")}, status=404)
        return self.get_response(request)
