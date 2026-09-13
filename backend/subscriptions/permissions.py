from rest_framework.permissions import BasePermission


class IsBusinessOwner(BasePermission):
    message = "Only the company owner can manage its subscription."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if getattr(user, "is_platform_admin", False):
            return True
        return bool(getattr(user, "role", None) and user.role.name == "Business Owner")
