"""Self-service password reset.

Two unauthenticated endpoints. The request step always answers the same way
whether or not the address is known, so it cannot be used to enumerate
accounts; it does say whether this server can send email at all, because
without SMTP the only path is an administrator resetting the password from
the Users screen and the person needs to be told that. The confirm step
uses Django's signed, single-use token (it embeds the password hash and
last-login timestamp, so it dies the moment either changes) and ends every
session the old credential opened.
"""

import logging

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.encoding import force_bytes, force_str
from django.utils.translation import gettext as _
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounts.models import User
from accounts.serializers import invalidate_sessions
from core import mailer
from core.activity import log_activity

logger = logging.getLogger(__name__)


def reset_link(user):
    origin = (getattr(settings, "PUBLIC_APP_ORIGIN", "") or "").rstrip("/")
    if not origin:
        return None
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    return f"{origin}/reset-password/?uid={uid}&token={token}"


def _send_reset_email(user, link):
    name = user.full_name or ""
    return mailer.send_bilingual(
        subject_ar="إعادة تعيين كلمة المرور",
        subject_en="Reset your Vezano Pro password",
        ar=[
            f"مرحباً {name}،".replace(" ،", "،"),
            "طُلبت إعادة تعيين كلمة مرور حسابك في فيزانو برو. "
            "اختر كلمة مرور جديدة من الرابط أدناه (صالح لمرة واحدة).",
            "إن لم تكن أنت من طلب ذلك فتجاهل هذه الرسالة؛ كلمة مرورك لم تتغير.",
        ],
        en=[
            f"Hello {name},".replace(" ,", ","),
            "A password reset was requested for your Vezano Pro account. "
            "Choose a new password with the one-time link below.",
            "If you did not ask for this, ignore this email; nothing has changed.",
        ],
        link=link,
        recipient=user.email,
    )


class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    def post(self, request):
        email = str(request.data.get("email") or "").strip().lower()
        if not email:
            return Response(
                {"email": ["This field is required."]}, status=status.HTTP_400_BAD_REQUEST
            )
        email_enabled = mailer.email_is_enabled() and bool(
            getattr(settings, "PUBLIC_APP_ORIGIN", "")
        )
        user = User.objects.filter(email__iexact=email, is_active=True).first()
        if user is not None and email_enabled:
            link = reset_link(user)
            if link:
                _send_reset_email(user, link)
                log_activity(
                    action="password_reset_requested", request=request, user=user,
                    entity_type="User", entity_id=user.pk,
                )
        # Same answer for a known and an unknown address.
        return Response({"accepted": True, "email_enabled": email_enabled})


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    def post(self, request):
        uid = request.data.get("uid") or ""
        token = request.data.get("token") or ""
        password = request.data.get("password") or ""
        try:
            user = User.objects.get(pk=force_str(urlsafe_base64_decode(uid)), is_active=True)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            user = None
        if user is None or not default_token_generator.check_token(user, token):
            return Response(
                {"detail": _("This reset link is invalid or has already been used.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            validate_password(password, user)
        except DjangoValidationError as exc:
            return Response({"password": list(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)
        user.set_password(password)
        # Chosen by the person themself: any administrator-set password it
        # replaces is no longer provisional.
        user.must_change_password = False
        user.save(update_fields=["password", "must_change_password"])
        invalidate_sessions(user)
        log_activity(
            action="password_reset", request=request, user=user,
            entity_type="User", entity_id=user.pk,
        )
        return Response({"reset": True})
