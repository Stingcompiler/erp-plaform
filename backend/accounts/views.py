from django.conf import settings
from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.cookies import clear_auth_cookies, set_auth_cookies
from accounts.models import Permission, Role, User
from accounts.serializers import (
    LoginSerializer,
    MeSerializer,
    PermissionSerializer,
    RoleSerializer,
    UserSerializer,
)
from core.activity import log_activity
from core.deletion import ArchiveOnDeleteMixin
from core.rbac import RoleModuleAccess, tenant_scope_error
from core.scoping import CompanyScopedModelViewSet
from org.store_mode import is_store_mode_allowed
from org.models import Company
from subscriptions.services import assert_capacity


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        scope_error = tenant_scope_error(user)
        if scope_error:
            detail = {
                "role_assignment_required": "Your account needs an assigned role.",
                "branch_assignment_required": "Your branch assignment is missing or inactive.",
                "company_assignment_required": "Your account needs an assigned company.",
            }.get(scope_error, "Your account assignment is invalid.")
            return Response(
                {"code": scope_error, "detail": f"{detail} Contact a company owner."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if not is_store_mode_allowed(user):
            owner = User.objects.filter(
                company_id=user.company_id, role__name="Business Owner", is_active=True
            ).first()
            log_activity(
                action="login_blocked",
                user=user,
                request=request,
                metadata={"reason": "store_mode_restricted"},
            )
            return Response(
                {
                    "code": "store_mode_restricted",
                    "detail": "The system is currently operating in shop mode.",
                    "owner_contact": owner.email if owner else "",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        refresh = RefreshToken.for_user(user)
        access = refresh.access_token

        response = Response(MeSerializer(user).data, status=status.HTTP_200_OK)
        set_auth_cookies(response, str(access), str(refresh))

        # Rule #8: login is a state-changing event and must be audited.
        log_activity(action="login", user=user, request=request)
        return response


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_cookie = request.COOKIES.get(settings.SIMPLE_JWT["AUTH_COOKIE_REFRESH"])
        # Blacklist the refresh token so it can't mint new access tokens after
        # logout (append-only invalidation, not a silent delete).
        if refresh_cookie:
            try:
                RefreshToken(refresh_cookie).blacklist()
            except TokenError:
                pass

        log_activity(action="logout", user=request.user, request=request)

        response = Response({"detail": "Logged out."}, status=status.HTTP_200_OK)
        clear_auth_cookies(response)
        return response


class RefreshView(APIView):
    """Issues a fresh access-token cookie from the refresh-token cookie."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        refresh_cookie = request.COOKIES.get(settings.SIMPLE_JWT["AUTH_COOKIE_REFRESH"])
        if not refresh_cookie:
            return Response({"detail": "No refresh token."}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            refresh = RefreshToken(refresh_cookie)
        except TokenError:
            return Response(
                {"detail": "Invalid refresh token."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        response = Response({"detail": "Refreshed."}, status=status.HTTP_200_OK)
        set_auth_cookies(response, str(refresh.access_token))
        return response


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(MeSerializer(request.user).data)


class UserViewSet(ArchiveOnDeleteMixin, CompanyScopedModelViewSet):
    capacity_resource = "users"
    """
    User administration, company-scoped like everything else: a company's
    admin sees and manages only their own company's users. Password is
    write-only via the serializer.

    Deactivated, never deleted. `Payment.recorded_by` and `verified_by` are
    SET_NULL, so removing the row would quietly strip the names off every
    payment that person handled — and those two names are exactly what proves
    segregation of duties held. `is_active=False` blocks the login (checked in
    the auth serializer) while leaving the attribution intact.
    """

    queryset = User.objects.select_related("role", "company", "branch").all()
    serializer_class = UserSerializer
    activity_entity_type = "User"
    branch_field = "branch"
    include_unassigned_branch_rows = False

    @transaction.atomic
    def perform_create(self, serializer):
        if self.request.user.company_id is None:
            return super().perform_create(serializer)
        company = Company.objects.select_for_update().get(pk=self.request.user.company_id)
        assert_capacity(company, "users")
        super().perform_create(serializer)

    @transaction.atomic
    def perform_update(self, serializer):
        target = User.objects.select_for_update().get(pk=serializer.instance.pk)
        role = serializer.validated_data.get("role", target.role)
        is_active = serializer.validated_data.get("is_active", target.is_active)
        removing_owner = (
            target.role
            and target.role.name == "Business Owner"
            and (not is_active or role is None or role.name != "Business Owner")
        )
        if removing_owner:
            active_owners = User.objects.select_for_update().filter(
                company_id=target.company_id,
                role__name="Business Owner",
                is_active=True,
            )
            if active_owners.count() <= 1:
                raise ValidationError(
                    {"role": "The company must retain at least one active owner."}
                )
        super().perform_update(serializer)

    def destroy(self, request, *args, **kwargs):
        # Deactivating yourself would lock you out of the account that has the
        # rights to undo it — in a single-admin company that bricks the tenant.
        if self.get_object().pk == request.user.pk:
            return Response(
                {"detail": "You cannot deactivate your own account."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        target = self.get_object()
        if target.role and target.role.name == "Business Owner":
            if User.objects.filter(
                company_id=target.company_id,
                role__name="Business Owner",
                is_active=True,
            ).count() <= 1:
                return Response(
                    {"detail": "The company must retain at least one active owner."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        return super().destroy(request, *args, **kwargs)


class RoleViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Roles are a fixed, seeded, platform-wide set (not per-company data), so
    they're read-only here and intentionally NOT company-scoped.
    """

    queryset = Role.objects.prefetch_related("permissions").all()
    serializer_class = RoleSerializer
    permission_classes = [IsAuthenticated, RoleModuleAccess]
    rbac_module = "users"

    def get_queryset(self):
        qs = super().get_queryset()
        if not self.request.user.is_platform_admin:
            qs = qs.exclude(scope_level=Role.SCOPE_PLATFORM)
        role_name = getattr(getattr(self.request.user, "role", None), "name", None)
        if role_name == "General Manager":
            qs = qs.exclude(name="Business Owner")
        elif role_name == "Branch Manager":
            qs = qs.filter(scope_level=Role.SCOPE_BRANCH).exclude(
                name="Branch Manager"
            )
        return qs


class PermissionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Permission.objects.all()
    serializer_class = PermissionSerializer
    permission_classes = [IsAuthenticated, RoleModuleAccess]
    rbac_module = "users"
