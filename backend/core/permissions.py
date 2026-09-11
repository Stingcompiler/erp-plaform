from rest_framework.permissions import SAFE_METHODS, BasePermission

from core.rbac import can_view_audit_log, role_can


class IsAuditViewer(BasePermission):
    """
    Gates the audit log to oversight roles: platform Super Administrators (who
    see every company's activity), the owner and general manager of a company
    (who see their own), and anyone with `settings` write access. Everyone else
    — branch and officer roles — is denied, so the trail can't leak activity to
    users who shouldn't see it.

    Membership lives in core.rbac.AUDIT_VIEWER_ROLES so the policy sits beside
    the other authority lists rather than being buried in a permission class.
    """

    message = "The audit log is restricted to administrators."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return can_view_audit_log(user)


class CanVerifyPayment(BasePermission):
    """
    Authorises payment verification/approval.

    Verification is a treasury responsibility, not a sales/purchasing one — so
    `finance` write qualifies even when the action happens to live on the sales
    or purchasing viewset. The owning module's own write access still qualifies
    too, so existing sales/purchasing managers keep verifying as before; this
    only widens access to finance controllers (CFO), never narrows it.

    The viewset declares which module it belongs to via `approval_module`.
    """

    message = "You are not permitted to verify payments."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if getattr(user, "is_platform_admin", False):
            return True
        own_module = getattr(view, "approval_module", None)
        return role_can(user, "finance", write=True) or (
            bool(own_module) and role_can(user, own_module, write=True)
        )


class IsPlatformAdminOrReadOnly(BasePermission):
    """
    Read allowed for any authenticated user (further narrowed to their own
    company by the viewset's queryset). Writes are restricted to platform-level
    Super Administrators — used for tenant-root resources like Company that a
    normal company user may view but not create/reshape.
    """

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return bool(request.user and request.user.is_authenticated)
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "is_platform_admin", False)
        )


class IsPlatformAdmin(BasePermission):
    """Allow access only to administrators who operate the Vezano platform."""

    message = "This area is restricted to platform administrators."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "is_platform_admin", False)
        )
