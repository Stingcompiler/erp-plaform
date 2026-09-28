from django.conf import settings
from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework.authentication import CSRFCheck
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.permissions import SAFE_METHODS
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed

from accounts.presence import touch_last_seen
from org.devices import is_revoked, requires_device
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


class CsrfFailed(PermissionDenied):
    """A cookie-authenticated write arrived without the CSRF token the page
    was given. The frontend reloads its identity (which reissues the cookie)
    and retries once before showing this."""

    default_code = "csrf_failed"
    default_detail = {
        "code": "csrf_failed",
        "detail": _("The request is missing its security token. Reload the page and try again."),
    }


def enforce_csrf(request):
    """Django's own CSRF check — the Origin/Referer test, then the cookie
    against the X-CSRFToken header — run the way DRF's SessionAuthentication
    runs it (review F15).

    The browser attaches the auth cookie to any request aimed at this host,
    including one a foreign page or an injected form on a same-origin public
    page sends; only the page's own scripts can read the csrftoken cookie and
    echo it in the header, so that is what proves the request came from the
    app. Bearer-header clients skip this: a header is never attached by the
    browser on its own.
    """

    def dummy_get_response(request):  # pragma: no cover - required signature
        return None

    check = CSRFCheck(dummy_get_response)
    check.process_request(request)
    reason = check.process_view(request, None, (), {})
    if reason:
        raise CsrfFailed()


class CookieJWTAuthentication(JWTAuthentication):
    """
    Authenticates from the access token stored in an HttpOnly cookie
    (PROJECT_RULES: JWT via HttpOnly cookies), or — for scripts and
    integrations that hold a token themselves — from an
    ``Authorization: Bearer`` header.

    Keeping the token in an HttpOnly cookie means client-side JS can't read it,
    which mitigates token theft via XSS. The cookie name is configured in
    settings.SIMPLE_JWT["AUTH_COOKIE"]. Because the browser sends that cookie
    on its own, a cookie-authenticated write must also pass the CSRF check;
    a header-authenticated one need not.
    """

    def authenticate(self, request):
        raw_token = request.COOKIES.get(settings.SIMPLE_JWT["AUTH_COOKIE"])
        from_cookie = bool(raw_token)
        if not raw_token:
            header = self.get_header(request)
            if header is None:
                return None
            raw_token = self.get_raw_token(header)
            if raw_token is None:
                return None
        validated_token = self.get_validated_token(raw_token)
        user = self.get_user(validated_token)
        device_id = validated_token.get("device")
        if device_id and is_revoked(user.company_id, device_id):
            raise AuthenticationFailed(
                _("This device was removed by the company."), code="device_revoked"
            )
        if not device_id and requires_device(user):
            # A token minted without a device (before device identity was
            # mandatory, or by hand) would let a company account work
            # uncounted against the plan's device limit (review F16).
            raise AuthenticationFailed(
                {"code": "device_required", "detail": _("Sign in again from this device.")},
                code="device_required",
            )
        if not is_store_mode_allowed(user):
            raise AuthenticationFailed(
                _("The system is currently operating in shop mode."),
                code="store_mode_restricted",
            )
        # A deleted company ends every session; a company suspended until
        # payment leaves its owner only the way to pay (core.company_access).
        from core.company_access import check_request

        check_request(user, request.path)
        if getattr(user, "must_change_password", False) and not request.path.startswith(
            PASSWORD_CHANGE_OPEN_PREFIXES
        ):
            raise PasswordChangeRequired()
        if from_cookie and request.method not in SAFE_METHODS:
            enforce_csrf(request)
        from core.timezone import activate_for_user

        activate_for_user(user)
        # Presence: at most one write every few minutes per user.
        touch_last_seen(user)
        return user, validated_token
