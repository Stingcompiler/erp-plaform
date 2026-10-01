"""The public trial form: duplicate check, then an email code, then the request.

Owner decisions (2026-10-01):

1. The form is validated and checked against existing requests before any
   email goes out. A request that is still open (submitted, under review,
   needs information, approved) or already provisioned blocks a new one
   when ANY of these is the same: the email (case-insensitive), the phone's
   last 9 digits, the company name or the contact name after folding
   (website.tracking.name_key). Rejected and withdrawn requests never block.
   The visitor only reads a generic "you already have a request" with the
   support WhatsApp; which field matched is never said, and the reference
   goes by email to the address on the existing request (at most once an
   hour per request).
2. Otherwise a 6-digit code goes to the email typed in the form
   (core.otp has the limits) and the form is kept in the cache under a
   random ``pending_id``. Nothing is written to the database yet.
3. The RegistrationRequest is created only when the code verifies — after
   the duplicate check runs again (two tabs, two forms) — and only then
   do the acknowledgement email and the team notice go out. A retry of
   the same ``request_uuid`` finds the request it already created.
"""

import logging

from django.db import transaction
from django.db.models import Q

from core import otp
from website.models import RegistrationRequest
from website.tracking import name_key, phone_key

logger = logging.getLogger(__name__)

PURPOSE = "trial"
# The states in which a request still stands for the company.
BLOCKING_STATES = (
    RegistrationRequest.SUBMITTED,
    RegistrationRequest.UNDER_REVIEW,
    RegistrationRequest.NEEDS_INFORMATION,
    RegistrationRequest.APPROVED,
    RegistrationRequest.PROVISIONED,
)
DUPLICATE_NOTICE_EVERY = 60 * 60  # seconds between "you already have a request" emails


def find_duplicate(data, *, exclude_uuid=None):
    """The open or provisioned request this form repeats, or None.

    Every key is an indexed column already on the row (lookup_phone,
    lookup_company, lookup_name are filled on save), so this is one query."""
    keys = Q(email__iexact=str(data.get("email") or "").strip())
    phone = phone_key(data.get("phone"))
    if phone:
        keys |= Q(lookup_phone=phone)
    company = name_key(data.get("company_name"))
    if company:
        keys |= Q(lookup_company=company)
    contact = name_key(data.get("contact_name"))
    if contact:
        keys |= Q(lookup_name=contact)
    rows = RegistrationRequest.objects.filter(status__in=BLOCKING_STATES).filter(keys)
    if exclude_uuid:
        rows = rows.exclude(request_uuid=exclude_uuid)
    return rows.order_by("-created_at", "-id").first()


def support_whatsapp():
    from website.seo import site_seo

    try:
        return site_seo().support_whatsapp or ""
    except Exception:  # noqa: BLE001 - the page works without it
        return ""


def duplicate_payload():
    from django.utils.translation import gettext as _

    return {
        "code": "duplicate_request",
        "detail": _(
            "You already have a request with us. Track it on the tracking page, or "
            "message us on WhatsApp."
        ),
        "message": {
            "ar": "لديك طلب قائم لدينا. تابعه من صفحة التتبّع أو راسلنا على واتساب.",
            "en": "You already have a request with us. Track it on the tracking page, "
                  "or message us on WhatsApp.",
        },
        "whatsapp": support_whatsapp(),
    }


def notify_existing(existing):
    """Email the existing request's own address its reference and the track
    link — off the request thread, at most once an hour per request."""
    from django.core.cache import cache

    if not cache.add(f"trial-duplicate-notice:{existing.pk}", 1, DUPLICATE_NOTICE_EVERY):
        return False
    from core import team_notify

    email, reference = existing.email, existing.public_reference
    contact, company = existing.contact_name, existing.company_name

    def work():
        _email_existing(email, reference, contact, company)

    team_notify.run_in_background(work, "trial-duplicate-notice")
    return True


def _email_existing(email, reference, contact, company):
    from core import mailer
    from website.views import _track_url

    return mailer.send_bilingual(
        subject_ar="لديك طلب قائم في فيزانو برو",
        subject_en="You already have a Vezano Pro request",
        ar=[
            f"مرحباً {contact}،",
            f"لديك طلب قائم لـ«{company}»، لذلك لم نفتح طلباً جديداً.",
            f"رقم طلبك: {reference}",
            "تابع حالته من صفحة التتبّع؛ سنرسل لك رمز تحقق على هذا البريد.",
            "إن لم تكن أنت من حاول التسجيل فتجاهل هذه الرسالة.",
        ],
        en=[
            f"Hello {contact},",
            f"You already have a request for “{company}”, so no new one was opened.",
            f"Your reference: {reference}",
            "Follow it on the tracking page; we email a verification code to this address.",
            "If you did not try to register, ignore this email.",
        ],
        link=_track_url(),
        preheader=f"{reference} · لديك طلب قائم · You already have a request",
        button_label_ar="تتبّع طلبك",
        button_label_en="Track your request",
        recipient=email,
    )


def send_code(email, code, company):
    minutes = otp.CODE_TTL // 60
    return otp.send_code_email(
        email, code,
        subject_ar="رمز تأكيد طلب التجربة",
        subject_en="Your trial request code",
        ar=[
            f"رمز تأكيد طلب «{company}» في فيزانو برو:",
            f"اكتبه في صفحة الطلب خلال {minutes} دقائق. لا تشاركه مع أحد.",
            "إن لم تطلب هذا الرمز فتجاهل الرسالة؛ لن يُفتح أي طلب.",
        ],
        en=[
            f"Your Vezano Pro code for the “{company}” trial request is shown above.",
            f"Enter it on the request page within {minutes} minutes. Never share it.",
            "If you did not ask for it, ignore this email; no request is opened.",
        ],
    )


def stored_form(validated):
    """The validated form as plain JSON for the cache (re-validated on verify)."""
    form = {}
    for field, value in validated.items():
        if field == "plan_version":
            value = value.pk if value is not None else None
        elif field == "request_uuid":
            value = str(value)
        form[field] = value
    return form


def _deliver(payload):
    return lambda code: send_code(payload["email"], code, payload["form"].get("company_name", ""))


def start(form, email, request):
    """Keep the form in a code challenge and email its first code; the
    challenge id. Raises core.otp.TooManySends / DeliveryFailed."""
    payload = {"form": form, "email": email}
    return otp.issue(PURPOSE, email, payload, request=request, deliver=_deliver(payload))


def resend(pending_id, request):
    """A new code for a pending form; its payload (core.otp errors pass through)."""
    payload = otp.peek(pending_id, purpose=PURPOSE)
    return otp.resend(pending_id, purpose=PURPOSE, request=request, deliver=_deliver(payload))


def create(validated):
    """(registration, created) for a verified form; acknowledgement and team
    notice only for a request created now."""
    from core import team_notify
    from website.views import _email_request_received

    with transaction.atomic():
        registration, created = RegistrationRequest.objects.get_or_create(
            request_uuid=validated["request_uuid"], defaults=validated,
        )
        if created:
            team_notify.registration_submitted(registration)
    if created:
        _email_request_received(registration)
    return registration, created
