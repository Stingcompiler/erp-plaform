from django.utils.translation import gettext_lazy as _
from rest_framework.permissions import BasePermission


class IsBusinessOwner(BasePermission):
    message = _("Only the company owner can manage its subscription.")

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        # Platform staff manage subscriptions through /api/platform/*; the
        # owner-facing views assume a company and would 500 (or import a
        # licence) for a company-less identity.
        if getattr(user, "is_platform_admin", False):
            return False
        return bool(getattr(user, "role", None) and user.role.name == "Business Owner")
