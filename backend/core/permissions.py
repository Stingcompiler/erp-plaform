from django.utils.translation import gettext_lazy as _
from rest_framework.permissions import SAFE_METHODS, BasePermission

from core.rbac import (
    RoleModuleAccess,
    can_approve_high_value,
    can_view_audit_log,
    report_areas_for,
    role_can,
    tenant_scope_error,
)
from core.entitlements import resolve_entitlements
from config.deployment import get_deployment_config
from rest_framework.exceptions import PermissionDenied


class EntitlementAccess(BasePermission):
    """Commercial access gate, independent from role and tenant permissions."""

    @staticmethod
    def _is_existing_create_replay(request, view):
        if request.method != "POST" or getattr(view, "action", None) != "create":
            return False
        client_uuid = request.data.get("client_uuid")
        if not client_uuid or not hasattr(view, "get_queryset"):
            return False
        try:
            queryset = view.get_queryset()
            queryset.model._meta.get_field("client_uuid")
            return queryset.filter(client_uuid=client_uuid).exists()
        except (AttributeError, TypeError, ValueError):
            return False

    def has_permission(self, request, view):
        if getattr(view, "entitlement_exempt", False):
            return True
        user = request.user
        if not (user and user.is_authenticated):
            return False
        scope_error = tenant_scope_error(user)
        if scope_error:
            raise PermissionDenied(scope_error)
        if getattr(user, "is_platform_admin", False):
            return False
        module = RoleModuleAccess()._module_for(view)
        decision = resolve_entitlements(getattr(user, "company", None))
        if not decision.allows_module(module):
            raise PermissionDenied(
                {
                    "code": "module_not_in_plan",
                    "detail": _("This module is not included in the current plan or licence."),
                }
            )
        if request.method not in SAFE_METHODS and not decision.allow_writes:
            replay_check = getattr(view, "is_completed_entitlement_replay", None)
            if (
                replay_check and replay_check(request)
            ) or self._is_existing_create_replay(request, view):
                return True
            code = (
                "license_read_only"
                if get_deployment_config().is_standalone
                else "subscription_read_only"
            )
            raise PermissionDenied(
                {
                    "code": code,
                    "detail": (
                        "Commercial access is read-only. The company owner can "
                        "review renewal details."
                    ),
                }
            )
        return True


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
            return False
        own_module = getattr(view, "approval_module", None)
        return role_can(user, "finance", write=True) or (
            bool(own_module) and role_can(user, own_module, write=True)
        )


class CanApproveSalaryAdvance(BasePermission):
    """Keep salary-advance decisions with financial approval authority.

    HR records and follows up the employee's request, but approving or
    rejecting it creates a financial obligation.  The same supervisory roles
    that approve high-value financial operations may therefore decide it.
    """

    message = _("Only a financial manager or an authorised executive may approve this.")

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and can_approve_high_value(user)
            and EntitlementAccess().has_permission(request, view)
        )


class IsPlatformAdminOrReadOnly(BasePermission):
    """
    Read allowed for any authenticated user (further narrowed to their own
    company by the viewset's queryset). Writes are restricted to platform-level
    Super Administrators — used for tenant-root resources like Company that a
    normal company user may view but not create/reshape.
    """

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if getattr(user, "is_platform_admin", False):
            return False
        return request.method in SAFE_METHODS


class IsPlatformAdmin(BasePermission):
    """Allow access only to members of the Vezano platform team.

    A read needs ``platform_view_capability`` when the view declares one
    (a view without it, such as the overview, is open to every member). A
    write needs the capability the view declares: ``platform_capability`` for
    the whole view, optionally overridden per action with
    ``platform_action_capabilities = {"verify": "..."}``. A view that declares
    no write capability keeps the old behaviour (any member may write).
    See core.platform_roles for the role -> capability map.
    """

    message = "This area is restricted to platform administrators."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated and getattr(user, "is_platform_admin", False)):
            return False
        from core.platform_roles import user_has_platform_capability

        if request.method in SAFE_METHODS:
            view_capability = getattr(view, "platform_view_capability", None)
            if view_capability is None or user_has_platform_capability(user, view_capability):
                return True
            self.message = "Your platform role does not include this area."
            return False
        action = getattr(view, "action", None)
        per_action = getattr(view, "platform_action_capabilities", {}) or {}
        capability = (
            per_action[action] if action in per_action
            else getattr(view, "platform_capability", None)
        )
        if capability is None:
            return True
        if user_has_platform_capability(user, capability):
            return True
        self.message = "Your platform role does not include this action."
        return False


class ReportAreaAccess(BasePermission):
    """Restrict each report endpoint to the department family it belongs to."""

    message = "Your role does not permit this report."

    def has_permission(self, request, view):
        return getattr(view, "report_area", None) in report_areas_for(request.user)


class PayrollReportAccess(BasePermission):
    """Payroll is shared oversight for HR and finance, but no other area."""

    message = "Your role does not permit this payroll report."

    def has_permission(self, request, view):
        if getattr(getattr(request.user, "role", None), "name", None) == "Branch Manager":
            return False
        return bool({"hr", "finance"}.intersection(report_areas_for(request.user)))
