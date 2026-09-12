from django.conf import settings
from rest_framework import status, viewsets
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
from core.scoping import CompanyScopedModelViewSet
from org.store_mode import is_store_mode_allowed


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        if not is_store_mode_allowed(user):
            owner = User.objects.filter(
                company_id=user.company_id, role__name="Business Owner", is_active=True
            ).first()
            log_activity(
                action="login_blocked", user=user, request=request,
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
            return Response(
                {"detail": "No refresh token."}, status=status.HTTP_401_UNAUTHORIZED
            )
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

    def destroy(self, request, *args, **kwargs):
        # Deactivating yourself would lock you out of the account that has the
        # rights to undo it — in a single-admin company that bricks the tenant.
        if self.get_object().pk == request.user.pk:
            return Response(
                {"detail": "You cannot deactivate your own account."},
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
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        if not self.request.user.is_platform_admin:
            qs = qs.exclude(scope_level=Role.SCOPE_PLATFORM)
        return qs


class PermissionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Permission.objects.all()
    serializer_class = PermissionSerializer
    permission_classes = [IsAuthenticated]
