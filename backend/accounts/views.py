from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
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
from accounts.presence import record_login
from accounts.serializers import (
    ChangePasswordSerializer,
    LoginSerializer,
    MeSerializer,
    PermissionSerializer,
    RoleSerializer,
    UserSerializer,
    UserDetailSerializer,
    invalidate_sessions,
)
from core import mailer
from core.activity import log_activity
from core.deletion import ArchiveOnDeleteMixin
from core.rbac import RoleModuleAccess, tenant_scope_error
from core.scoping import CompanyScopedModelViewSet
from rest_framework.decorators import action

from accounts.removal import attribution_of
from subscriptions.permissions import IsBusinessOwner
from org.devices import DeviceRefused, is_revoked, register_device, requires_device
from org.store_mode import is_store_mode_allowed
from org.models import Company
from subscriptions.services import assert_capacity


def _lockout_key(email):
    return f"login-lockout:{email.strip().lower()}"


def failed_login_count(email):
    return int(cache.get(_lockout_key(email), 0) or 0)


def clear_failed_logins(email):
    cache.delete(_lockout_key(email))


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        # Per-account lockout, alongside the per-IP throttle. The IP throttle
        # alone is defeated by rotating addresses (or forging the forwarded
        # header); this counter follows the account being attacked instead.
        email = str(request.data.get("email") or "")
        attempts = settings.LOGIN_LOCKOUT_ATTEMPTS
        if email and failed_login_count(email) >= attempts:
            log_activity(
                action="login_blocked",
                request=request,
                metadata={"reason": "account_locked", "email": email.strip().lower()},
            )
            return Response(
                {
                    "code": "account_locked",
                    "detail": "Too many failed sign-in attempts. Try again later.",
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        serializer = LoginSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            if email:
                key = _lockout_key(email)
                cache.add(key, 0, settings.LOGIN_LOCKOUT_SECONDS)
                try:
                    cache.incr(key)
                except ValueError:
                    cache.set(key, 1, settings.LOGIN_LOCKOUT_SECONDS)
            raise ValidationError(serializer.errors)
        user = serializer.validated_data["user"]
        clear_failed_logins(email)
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

        device_id = str(request.data.get("device_id") or "").strip()
        try:
            device = register_device(user.company, device_id, user, request)
        except DeviceRefused as refused:
            owner = User.objects.filter(
                company_id=user.company_id, role__name="Business Owner", is_active=True
            ).first()
            log_activity(
                action="login_blocked", user=user, request=request,
                metadata={"reason": refused.code, "device_id": device_id[:64]},
            )
            detail = {
                "device_limit_reached": "This company's plan has no room for another device.",
                "device_revoked": (
                    "This device was removed by the company. Ask the owner to allow it again."
                ),
                "device_required": (
                    "Sign in from the Vezano app or website so this device can be "
                    "identified; company accounts cannot sign in without a device id."
                ),
            }[refused.code]
            return Response(
                {
                    "code": refused.code,
                    "detail": detail,
                    "limit": refused.limit,
                    "owner_contact": owner.email if owner else "",
                },
                status=(
                    status.HTTP_400_BAD_REQUEST if refused.code == "device_required"
                    else status.HTTP_403_FORBIDDEN
                ),
            )

        refresh = RefreshToken.for_user(user)
        if device is not None:
            # Carried by every token this session mints, so revoking the
            # device ends the session (accounts.authentication).
            refresh["device"] = device.device_id
        access = refresh.access_token

        response = Response(MeSerializer(user).data, status=status.HTTP_200_OK)
        set_auth_cookies(response, str(access), str(refresh))

        # Rule #8: login is a state-changing event and must be audited.
        log_activity(
            action="login", user=user, request=request,
            metadata={"device_id": device.device_id} if device is not None else None,
        )
        record_login(user)
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
    """Rotates the refresh-token cookie and issues a fresh access-token cookie.

    Rotation is what makes ROTATE_REFRESH_TOKENS / BLACKLIST_AFTER_ROTATION
    mean something: the presented refresh token is blacklisted and a new one
    set, so a copied cookie stops working the moment the legitimate client
    refreshes, instead of staying valid for the full seven days."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        refresh_cookie = request.COOKIES.get(settings.SIMPLE_JWT["AUTH_COOKIE_REFRESH"])
        if not refresh_cookie:
            return Response({"detail": "No refresh token."}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            refresh = RefreshToken(refresh_cookie)
            user = User.objects.get(pk=refresh["user_id"], is_active=True)
        except (TokenError, KeyError, User.DoesNotExist, ValueError):
            response = Response(
                {"detail": "Invalid refresh token."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
            clear_auth_cookies(response)
            return response

        device_id = refresh.get("device")
        if device_id and is_revoked(user.company_id, device_id):
            response = Response(
                {"code": "device_revoked", "detail": "This device was removed by the company."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
            clear_auth_cookies(response)
            return response
        if not device_id and requires_device(user):
            # A session minted before device identity was mandatory: it ends
            # here and the next sign-in registers the device.
            response = Response(
                {"code": "device_required", "detail": "Sign in again from this device."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
            clear_auth_cookies(response)
            return response
        rotated = RefreshToken.for_user(user)
        if device_id:
            rotated["device"] = device_id
        try:
            refresh.blacklist()
        except (TokenError, AttributeError):
            pass

        response = Response({"detail": "Refreshed."}, status=status.HTTP_200_OK)
        set_auth_cookies(response, str(rotated.access_token), str(rotated))
        return response


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(MeSerializer(request.user).data)


class ChangePasswordView(APIView):
    """Replace one's own password. Ends every other session and hands this
    one fresh cookies, so the person who just proved they hold both the old
    and the new secret is the only one still signed in."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = request.user
        user.set_password(serializer.validated_data["new_password"])
        user.must_change_password = False
        user.save(update_fields=["password", "must_change_password"])
        invalidate_sessions(user)
        refresh = RefreshToken.for_user(user)
        response = Response(MeSerializer(user).data)
        set_auth_cookies(response, str(refresh.access_token), str(refresh))
        log_activity(
            action="password_changed", request=request, entity_type="User", entity_id=user.pk,
        )
        return response


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

    capacity_resource = "users"

    queryset = User.objects.select_related("role", "company", "branch").all()
    serializer_class = UserSerializer
    activity_entity_type = "User"
    branch_field = "branch"
    include_unassigned_branch_rows = False

    def get_serializer_class(self):
        if self.action == "retrieve":
            return UserDetailSerializer
        return UserSerializer

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
        password_set = bool(serializer.validated_data.get("password"))
        by_someone_else = password_set and target.pk != self.request.user.pk
        if set(serializer.validated_data) == {"password"} and by_someone_else:
            # Nothing but the password changed: one clear audit row, not an
            # "update" that names no field because the field is a secret.
            serializer.save()
        else:
            super().perform_update(serializer)
        if by_someone_else:
            self._record_admin_password_reset(target)

    def _record_admin_password_reset(self, target):
        """Rule #8 for the one change the audit trail otherwise cannot show:
        the value is secret, so the event itself must say what happened and
        who did it. The person is told the same by email, so a reset they
        did not ask for cannot pass unnoticed."""
        actor = self.request.user
        log_activity(
            action="password_reset_by_admin", request=self.request,
            entity_type="User", entity_id=target.pk,
            metadata={"target_email": target.email, "target_name": target.full_name},
        )
        actor_name = actor.full_name or actor.email
        when = timezone.localtime().strftime("%Y-%m-%d %H:%M")
        mailer.send_bilingual(
            subject_ar="تم تغيير كلمة مرور حسابك",
            subject_en="Your Vezano password was changed",
            ar=[
                f"مرحباً {target.full_name or target.email}،",
                f"قام {actor_name} بتعيين كلمة مرور جديدة لحسابك في فيزانو بتاريخ {when}.",
                "عند تسجيل دخولك التالي سيُطلب منك اختيار كلمة مرور خاصة بك قبل متابعة العمل.",
                "إن لم تكن على علم بهذا التغيير فتواصل مع مالك الشركة فورًا.",
            ],
            en=[
                f"Hello {target.full_name or target.email},",
                f"{actor_name} set a new password for your Vezano account on {when}.",
                "At your next sign-in you will be asked to choose your own password "
                "before continuing.",
                "If you were not expecting this, contact your business owner right away.",
            ],
            recipient=target.email,
        )

    def _guard_removal(self, target, request):
        """Shared refusals for deactivating or removing an account."""
        if target.pk == request.user.pk:
            return "You cannot deactivate your own account."
        if target.role and target.role.name == "Business Owner":
            remaining = User.objects.filter(
                company_id=target.company_id,
                role__name="Business Owner",
                is_active=True,
            ).exclude(pk=target.pk).exists()
            if not remaining:
                return "The company must retain at least one active owner."
        return None

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, IsBusinessOwner])
    @transaction.atomic
    def remove(self, request, pk=None):
        """The owner removes an account for good.

        An account that never recorded anything is deleted; one that carries
        attribution is deactivated instead, and the response names what is
        holding it, so the owner is told the truth rather than silently given
        a different outcome.
        """
        target = self.get_object()
        refusal = self._guard_removal(target, request)
        if refusal:
            return Response({"detail": refusal}, status=status.HTTP_400_BAD_REQUEST)
        attribution = attribution_of(target)
        email, name, pk = target.email, target.full_name, target.pk
        if attribution:
            if target.is_active:
                target.is_active = False
                target.save(update_fields=["is_active"])
            log_activity(
                action="archive", request=request, entity_type="User", entity_id=pk,
                metadata={"target_email": email, "kept_for_audit": attribution},
            )
            return Response({
                "removed": False,
                "code": "kept_for_audit",
                "records": attribution,
            })
        target.delete()
        log_activity(
            action="delete", request=request, entity_type="User", entity_id=pk,
            metadata={"target_email": email, "target_name": name},
        )
        return Response({"removed": True})

    def destroy(self, request, *args, **kwargs):
        # Deactivating yourself would lock you out of the account that has the
        # rights to undo it — in a single-admin company that bricks the tenant,
        # and a company with no active owner cannot be administered at all.
        refusal = self._guard_removal(self.get_object(), request)
        if refusal:
            return Response({"detail": refusal}, status=status.HTTP_400_BAD_REQUEST)
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
