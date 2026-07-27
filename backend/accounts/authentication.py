from django.conf import settings
from rest_framework_simplejwt.authentication import JWTAuthentication


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
        return self.get_user(validated_token), validated_token
