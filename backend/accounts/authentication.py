from django.conf import settings
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed

from accounts.presence import touch_last_seen
from org.store_mode import is_store_mode_allowed


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
        if not is_store_mode_allowed(user):
            raise AuthenticationFailed(
                "The system is currently operating in shop mode.",
                code="store_mode_restricted",
            )
        from core.timezone import activate_for_user

        activate_for_user(user)
        # Presence: at most one write every few minutes per user.
        touch_last_seen(user)
        return user, validated_token
