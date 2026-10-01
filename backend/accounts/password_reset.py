"""Password reset by email code (owner decision, 2026-10-01: no reset links).

    POST /auth/password-reset/          {email}            -> 202 {challenge_id, resend_after,
                                                               email_enabled}
    POST /auth/password-reset/resend/   {challenge_id}     -> 202 {challenge_id, resend_after}
    POST /auth/password-reset/verify/   {challenge_id, code} -> {reset_token, expires_in}
    POST /auth/password-reset/confirm/  {reset_token, password} -> {reset: true}

The request step answers the same way whether or not the address has an
active account: an unknown address gets a decoy challenge (core.otp) that
sends nothing and can never verify, but resends, expires and runs out of
budget exactly like a real one; the real email goes out on a background
thread so timing tells nothing either. The answer does say whether this
server can send email at all, because without SMTP the only path is an
administrator setting the password from the Users screen.

A verified code buys a reset token: signed (salt ``password-reset``), 10
minutes, single use (a marker in the cache), bound to the account's current
password hash and last sign-in, so any password change or sign-in in the
meantime kills it. Setting the password ends every session the old one
opened and is logged.

An administrator (Users screen, platform team) starts the same challenge
for someone (``start_for_user``): the code goes to the person with a link
to /forgot-password that opens on the code step. The administrator is told
only that a code went out — never the code.

The old uid/token links are retired: such a request is refused with
``link_flow_retired`` so the page can explain.
"""

import hashlib
import logging
import secrets
import threading
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core import signing
from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import close_old_connections
from django.utils.translation import gettext as _
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounts.models import User
from accounts.serializers import invalidate_sessions
from core import mailer, otp
from core.activity import log_activity

logger = logging.getLogger(__name__)

PURPOSE = "password_reset"
TOKEN_SALT = "password-reset"
TOKEN_TTL = 10 * 60  # seconds a reset token lasts after the code verified
_USED_KEY = "password-reset-used:{}"


# ---------------------------------------------------------------- email

def _greeting(user):
    name = (user.full_name or "").strip()
    return (f"مرحباً {name}،" if name else "مرحباً،"), (f"Hello {name}," if name else "Hello,")


def _email_code(user, code, primary=None, *, actor_name=None, link=None):
    minutes = otp.CODE_TTL // 60
    hello_ar, hello_en = _greeting(user)
    if actor_name:
        why_ar = f"طلب {actor_name} إعادة تعيين كلمة مرور حسابك في فيزانو برو."
        why_en = f"{actor_name} started a password reset for your Vezano Pro account."
    else:
        why_ar = "طُلبت إعادة تعيين كلمة مرور حسابك في فيزانو برو."
        why_en = "A password reset was requested for your Vezano Pro account."
    where_ar = "من الزر أدناه" if link else "في صفحة استعادة كلمة المرور"
    where_en = "on the page the button below opens" if link else "on the password reset page"
    return otp.send_code_email(
        user.email, code,
        subject_ar="رمز إعادة تعيين كلمة المرور",
        subject_en="Your Vezano Pro password reset code",
        preheader=(
            f"رمز إعادة التعيين صالح {minutes} دقائق · "
            f"Your reset code is valid for {minutes} minutes"
        ),
        ar=[
            hello_ar,
            f"{why_ar} رمز التحقق مكتوب بخط كبير في هذه الرسالة.",
            f"اكتبه {where_ar} خلال {minutes} دقائق، ثم اختر كلمة مرور جديدة. "
            "لا تشاركه مع أحد؛ فريقنا لن يطلبه منك أبدًا.",
            "إن لم تطلب ذلك فتجاهل هذه الرسالة؛ كلمة مرورك لم تتغير.",
        ],
        en=[
            hello_en,
            f"{why_en} Your verification code is set large in this email.",
            f"Enter it {where_en} within {minutes} minutes, then choose a new password. "
            "Never share it; our team will never ask for it.",
            "If you did not ask for this, ignore this email; your password has not changed.",
        ],
        primary=primary,
        link=link,
        button_label_ar="افتح صفحة إعادة التعيين",
        button_label_en="Open the reset page",
    )


def _in_background(work):
    """Run ``work`` off the request path: the answer for a known address
    must not take measurably longer than for an unknown one (an SMTP round
    trip is hundreds of milliseconds), or timing would tell which addresses
    have accounts. Tests (and PASSWORD_RESET_EMAIL_BACKGROUND=False) run it
    inline so the outbox can be read at once."""
    if not getattr(settings, "PASSWORD_RESET_EMAIL_BACKGROUND", True):
        work()
        return

    def run():
        try:
            work()
        except Exception:  # noqa: BLE001 - a failed email is logged, never raised
            logger.exception("password reset email failed")
        finally:
            close_old_connections()

    threading.Thread(target=run, name="password-reset-email", daemon=True).start()


def _background_delivery(user, primary, on_sent=None):
    """A core.otp ``deliver`` that queues the code email and reports it
    sent, so a known address answers as fast as an unknown one."""
    def deliver(code):
        def work():
            if on_sent:
                on_sent()
            _email_code(user, code, primary)

        _in_background(work)
        return True

    return deliver


def reset_page_link(email, challenge_id):
    """/forgot-password opened on the code step for ``challenge_id``, or None
    when no public origin is configured."""
    origin = (getattr(settings, "PUBLIC_APP_ORIGIN", "") or "").rstrip("/")
    if not origin:
        return None
    return f"{origin}/forgot-password/?{urlencode({'email': email, 'challenge': challenge_id})}"


# ---------------------------------------------------------------- challenges

def _subject(user):
    return f"user:{user.pk}"


def start(email, request):
    """The challenge id for a reset request of ``email`` — a real one when an
    active account has it and this server can email, a decoy otherwise.
    Raises core.otp.TooManySends past the hourly budgets."""
    user = None
    if mailer.email_is_enabled():
        user = User.objects.filter(email__iexact=email, is_active=True).first()
    if user is None or not user.email:
        return otp.issue(PURPOSE, f"email:{email}", {"user": None}, request=request, decoy=True)
    primary = mailer.primary_language()  # read here: the worker has no active language

    def logged():
        log_activity(action="password_reset_requested", request=request, user=user,
                     entity_type="User", entity_id=user.pk)

    return otp.issue(PURPOSE, _subject(user), {"user": user.pk}, request=request,
                     deliver=_background_delivery(user, primary, on_sent=logged))


def resend(challenge_id, request):
    """A new code for a live challenge (decoys included); core.otp errors."""
    payload = otp.peek(challenge_id, purpose=PURPOSE)
    # One lookup either way (a decoy looks up pk 0), so timing matches.
    user = User.objects.filter(pk=payload.get("user") or 0, is_active=True).first()
    if user is None and payload.get("user"):
        # The account was deactivated since: nothing to send.
        otp.drop(challenge_id)
        raise otp.Expired(otp.Expired.code)
    deliver = _background_delivery(user, mailer.primary_language()) if user else None
    return otp.resend(challenge_id, purpose=PURPOSE, request=request, deliver=deliver)


def start_for_user(user, actor, request=None):
    """An administrator's reset for ``user``: the same challenge, the code
    emailed at once (so failure can be reported) with a link to the code
    step. Returns the challenge id; raises core.otp.TooManySends or
    DeliveryFailed (email off or refused)."""
    if not mailer.email_is_enabled() or not user.email:
        raise otp.DeliveryFailed(otp.DeliveryFailed.code)
    challenge_id = otp.new_id()
    link = reset_page_link(user.email, challenge_id)
    actor_name = (getattr(actor, "full_name", "") or getattr(actor, "email", "") or "").strip()
    otp.issue(
        PURPOSE, _subject(user), {"user": user.pk}, challenge_id=challenge_id,
        deliver=lambda code: _email_code(user, code, actor_name=actor_name, link=link),
    )
    log_activity(
        action="password_reset_code_by_admin", request=request,
        entity_type="User", entity_id=user.pk,
        metadata={"target_email": user.email, "target_name": user.full_name},
    )
    return challenge_id


# ---------------------------------------------------------------- reset token

def _state(user):
    """Changes whenever the password or the last sign-in does."""
    last = user.last_login.isoformat() if user.last_login else ""
    return hashlib.sha256(f"{user.password}|{last}".encode()).hexdigest()[:32]


def make_reset_token(user):
    return signing.dumps(
        {"u": user.pk, "s": _state(user), "j": secrets.token_urlsafe(12),
         "x": int(otp.now() + TOKEN_TTL)},
        salt=TOKEN_SALT,
    )


def read_reset_token(token):
    """(user, token id) for a live, unused token whose account has not
    changed since; None otherwise."""
    try:
        data = signing.loads(str(token or ""), salt=TOKEN_SALT)
    except signing.BadSignature:
        return None
    if not isinstance(data, dict) or int(data.get("x") or 0) <= otp.now():
        return None
    jti = str(data.get("j") or "")
    if not jti or cache.get(_USED_KEY.format(jti)):
        return None
    user = User.objects.filter(pk=data.get("u"), is_active=True).first()
    if user is None or data.get("s") != _state(user):
        return None
    return user, jti


def _spend_token(jti):
    """True for the one caller that gets to use the token."""
    return cache.add(_USED_KEY.format(jti), True, TOKEN_TTL + 60)


# ---------------------------------------------------------------- answers

def _error(code, http_status, **extra):
    """Every refusal carries a stable ``code`` the page translates."""
    messages = {
        "code_expired": _("This code has expired. Ask for a new one."),
        "wrong_code": _("That code is not right. Check the email and try again."),
        "too_many_attempts": _("Too many wrong codes. Ask for a new one."),
        "resend_cooldown": _("Wait a moment before asking for another code."),
        "too_many_codes": _("Too many codes were sent. Try again later."),
        "email_unavailable": _("The code could not be emailed right now."),
        "reset_expired": _(
            "This reset has expired or was already used. Ask for a new code."
        ),
        "link_flow_retired": _(
            "Password reset links are no longer used. Ask for a code by email instead."
        ),
    }
    response = Response({"code": code, "detail": messages.get(code, code), **extra},
                        status=http_status)
    if extra.get("retry_after"):
        response["Retry-After"] = str(extra["retry_after"])
    return response


def otp_failure(exc):
    if isinstance(exc, (otp.Cooldown, otp.TooManySends)):
        return _error(exc.code, status.HTTP_429_TOO_MANY_REQUESTS, retry_after=exc.retry_after)
    if isinstance(exc, otp.WrongCode):
        return _error(exc.code, status.HTTP_400_BAD_REQUEST, attempts_left=exc.attempts_left)
    if isinstance(exc, otp.DeliveryFailed):
        return _error(exc.code, status.HTTP_503_SERVICE_UNAVAILABLE)
    return _error(exc.code, status.HTTP_400_BAD_REQUEST)


def admin_reset(target, request):
    """The answer to an administrator's "send a reset code" for ``target``
    (refusals are the caller's): what went out and where — never the code,
    and not the challenge either, which only the person's email carries."""
    if not target.is_active:
        return Response({"detail": _("This account is deactivated.")},
                        status=status.HTTP_400_BAD_REQUEST)
    try:
        start_for_user(target, request.user, request)
    except otp.OtpError as exc:
        return otp_failure(exc)
    return Response({
        "sent": True,
        "email_masked": otp.mask_email(target.email),
        "expires_in": otp.CODE_TTL,
    }, status=status.HTTP_202_ACCEPTED)


def _challenge_body(challenge_id, **extra):
    return {"challenge_id": challenge_id, "resend_after": otp.RESEND_AFTER,
            "expires_in": otp.CODE_TTL, **extra}


def _data(request):
    return request.data if isinstance(request.data, dict) else {}


class _ResetView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        return response


class PasswordResetRequestView(_ResetView):
    def post(self, request):
        email = str(_data(request).get("email") or "").strip().lower()
        if not email or "@" not in email or len(email) > 254:
            return Response({"email": [_("Enter a valid email address.")]},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            challenge_id = start(email, request)
        except otp.OtpError as exc:
            return otp_failure(exc)
        # The same answer for a known and an unknown address.
        return Response(_challenge_body(challenge_id, email_enabled=mailer.email_is_enabled()),
                        status=status.HTTP_202_ACCEPTED)


class PasswordResetResendView(_ResetView):
    def post(self, request):
        challenge_id = str(_data(request).get("challenge_id") or "")
        try:
            resend(challenge_id, request)
        except otp.OtpError as exc:
            return otp_failure(exc)
        return Response(_challenge_body(challenge_id), status=status.HTTP_202_ACCEPTED)


class PasswordResetVerifyView(_ResetView):
    throttle_scope = "password_reset_verify"

    def post(self, request):
        data = _data(request)
        try:
            payload = otp.verify(str(data.get("challenge_id") or ""), data.get("code"),
                                 purpose=PURPOSE)
        except otp.OtpError as exc:
            return otp_failure(exc)
        user = User.objects.filter(pk=payload.get("user"), is_active=True).first()
        if user is None:
            return _error("code_expired", status.HTTP_400_BAD_REQUEST)
        return Response({"reset_token": make_reset_token(user), "expires_in": TOKEN_TTL})


class PasswordResetConfirmView(_ResetView):
    throttle_scope = "password_reset_verify"

    def post(self, request):
        data = _data(request)
        token = data.get("reset_token")
        if not token:
            if data.get("uid") or data.get("token"):
                return _error("link_flow_retired", status.HTTP_410_GONE)
            return _error("reset_expired", status.HTTP_400_BAD_REQUEST)
        found = read_reset_token(token)
        if found is None:
            return _error("reset_expired", status.HTTP_400_BAD_REQUEST)
        user, jti = found
        password = str(data.get("password") or "")
        try:
            validate_password(password, user)
        except DjangoValidationError as exc:
            return Response({"password": list(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)
        if not _spend_token(jti):
            return _error("reset_expired", status.HTTP_400_BAD_REQUEST)
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
