from django.conf import settings
from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed

from accounts.presence import touch_last_seen
from org.devices import is_revoked
from org.store_mode import is_store_mode_allowed

# While a password set by an administrator is still in use, the only things
# the person may do are find out who they are, sign out, and replace it.
# The identity call and its companions stay open so the app shell can load
# far enough to show the change-password screen.
PASSWORD_CHANGE_OPEN_PREFIXES = (
    "/api/auth/",
    "/api/rbac/access/",
    "/api/ops/preferences/",
    "/api/health/",
)


class PasswordChangeRequired(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "password_change_required"
    default_detail = {
        "code": "password_change_required",
        "detail": _("Choose your own password before continuing."),
    }


class CookieJWTAuthentication(JWTAuthentication):
    """
    Authenticates from the access token stored in an HttpOnly cookie instead
    of the Authorization header (PROJECT_RULES: JWT via HttpOnly cookies).

    Keeping the token in an HttpOnly cookie means client-side JS can't read it,
    which mitigates token theft via XSS. The cookie name is configured in
    settings.SIMPLE_JWT["AUTH_COOKIE"].
    """

    def authenticate(self, request):
        raw_token = request.COOKIES.get(settings.SIMPLE_JWT["AUTH_COOKIE"])
        if not raw_token:
            return None
        validated_token = self.get_validated_token(raw_token)
        user = self.get_user(validated_token)
        device_id = validated_token.get("device")
        if device_id and is_revoked(user.company_id, device_id):
            raise AuthenticationFailed(
                "This device was removed by the company.", code="device_revoked"
            )
        if not is_store_mode_allowed(user):
            raise AuthenticationFailed(
                "The system is currently operating in shop mode.",
                code="store_mode_restricted",
            )
        if getattr(user, "must_change_password", False) and not request.path.startswith(
            PASSWORD_CHANGE_OPEN_PREFIXES
        ):
            raise PasswordChangeRequired()
        from core.timezone import activate_for_user

        activate_for_user(user)
        # Presence: at most one write every few minutes per user.
        touch_last_seen(user)
        return user, validated_token
