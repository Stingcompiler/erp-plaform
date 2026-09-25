"""vezano.app/track/ — one search box for everything a person may be waiting
on from Vezano or from a store on it.

It finds, with the matching rules and limits of the store tracking page
(website.tracking, which this reuses rather than repeats):

- web orders from any store whose public page is published, each labelled
  with the store and linked to that store's tracking page. Never the private
  token link: the store page does not show it for a search either, and here
  a name, email or phone search would hand anyone the full order;
- registration requests (R…) and demo requests (D…) sent to Vezano;
- subscription payments a company recorded, by the full transfer reference
  from the bank app (the only reference a company can quote for one).

Same exposure as the store page: the last 90 days, at most 10 results in
all, exact matches only (reference, email, the phone's last 9 digits, or a
name after folding), no phone / email / address / full name in any result,
one miss message, and the same per-address lookup budget. The response
carries no query and is never cached; only counts are logged.
"""

import logging
import re
from datetime import timedelta

from django.utils import timezone

from website import tracking

logger = logging.getLogger(__name__)

# W = web order, R = registration request, D = demo request.
REFERENCE = re.compile(r"^[WRD][A-Z0-9]{6}$")
# A bank-app transaction id is long; shorter strings are never tried as one.
TRANSFER_REFERENCE_MIN = 8


def _pick(language, ar, en):
    return ar if language == "ar" else en


# ---------------------------------------------------------------- web orders

def _orders():
    from website.models import PublicOrder

    since = timezone.now() - timedelta(days=tracking.LOOKUP_DAYS)
    return (
        PublicOrder.objects.filter(
            created_at__gte=since, website__is_published=True, company__is_active=True,
        )
        .select_related("branch", "company", "website")
        .prefetch_related("lines", "payments", "events")
        .order_by("-created_at", "-id")
    )


def _order_item(order, language, who):
    from website.public_pages import _display_name

    view = tracking.public_view(order, language, who=who)
    view.pop("track_path", None)
    slug = order.company.slug
    view.update({
        "kind": "order",
        "store_name": _display_name(order.website),
        "store_path": f"/s/{slug}/",
        "store_track_path": f"/s/{slug}/track/",
    })
    return view


# ---------------------------------------------------------------- platform requests

REGISTRATION_STATES = {
    "submitted": ("استلمنا طلبك — قيد المراجعة", "Received — under review", "pending"),
    "under_review": ("قيد المراجعة", "Under review", "pending"),
    "needs_information": ("نحتاج معلومات إضافية", "We need more information", "warn"),
    "approved": ("تمت الموافقة — نجهّز مساحة العمل", "Approved — preparing your workspace", "ok"),
    "provisioned": ("تم التفعيل — تحقق من بريدك", "Activated — check your email", "ok"),
    "rejected": ("مرفوض", "Rejected", "closed"),
    "withdrawn": ("سُحب الطلب", "Withdrawn", "closed"),
}

DEMO_STATES = {
    "new": ("استلمنا طلبك — سنتواصل معك", "Received — we will contact you", "pending"),
    "contacted": ("تواصلنا معك", "We contacted you", "ok"),
    "qualified": ("قيد المتابعة", "In follow-up", "ok"),
    "closed": ("مغلق", "Closed", "closed"),
}

PAYMENT_STATES = {
    "pending": ("قيد التحقق", "Being checked", "pending"),
    "verified": ("تم التحقق — أُضيف إلى اشتراكك", "Verified — added to your subscription", "ok"),
    "rejected": ("مرفوض", "Rejected", "closed"),
}


def _registration_next(row, language):
    standalone = row.delivery_mode == "standalone"
    if row.status in ("submitted", "under_review"):
        if standalone:
            return _pick(
                language,
                "نرد عليك بعرض سعر الرخصة ودليل التركيب على بريدك.",
                "We reply with a licence quote and the installation guide by email.",
            )
        return _pick(
            language,
            "نراجع الطلبات ونفعّلها في نفس اليوم، ثم يصل رابط تفعيل حساب المالك إلى بريدك.",
            "We review and activate requests the same day; the owner activation link "
            "then arrives in your email.",
        )
    if row.status == "needs_information":
        return _pick(
            language,
            "سنتواصل معك بالهاتف أو البريد لإكمال الطلب، ويمكنك أيضاً مراسلتنا على واتساب.",
            "We will reach you by phone or email to complete the request; you can also "
            "message us on WhatsApp.",
        )
    if row.status == "approved":
        return _pick(
            language,
            "يصل رابط تفعيل حساب المالك إلى بريدك قريباً.",
            "The owner activation link arrives in your email shortly.",
        )
    if row.status == "provisioned":
        return _pick(
            language,
            "افتح رابط التفعيل في البريد الذي أرسلناه لتعيين كلمة المرور ثم سجّل الدخول. "
            "لم يصلك؟ تفقّد الرسائل غير المرغوبة أو تواصل معنا.",
            "Open the activation link in the email we sent to set your password, then sign "
            "in. Did not get it? Check the spam folder or contact us.",
        )
    if row.status == "rejected":
        return _pick(
            language, "لأي سؤال تواصل معنا.", "Contact us if you have any question.",
        )
    return ""


def _demo_next(row, language):
    if row.status != "new":
        return ""
    channel = {
        "whatsapp": ("على واتساب", "on WhatsApp"),
        "call": ("باتصال هاتفي", "by phone"),
        "email": ("بالبريد", "by email"),
    }.get(row.preferred_channel, ("", ""))
    return _pick(
        language,
        f"نتواصل معك {channel[0]} خلال يوم عمل.".replace("  ", " "),
        f"We contact you {channel[1]} within a working day.".replace("  ", " "),
    )


def _state(states, status, language):
    ar, en, tone = states.get(status, (status, status, "pending"))
    return _pick(language, ar, en), tone


def _registration_item(row, language, by_reference):
    label, tone = _state(REGISTRATION_STATES, row.status, language)
    reason = row.public_note if row.status in ("rejected", "needs_information") else ""
    return {
        "kind": "registration",
        "reference": row.public_reference,
        "created_at": row.created_at,
        "status": row.status,
        "status_label": label,
        "tone": tone,
        # The company is named only to whoever holds the exact reference.
        "customer": row.company_name if by_reference else tracking.initials(row.company_name),
        "standalone": row.delivery_mode == "standalone",
        "reason": reason,
        "next": _registration_next(row, language),
    }


def _demo_item(row, language, by_reference):
    label, tone = _state(DEMO_STATES, row.status, language)
    return {
        "kind": "demo",
        "reference": row.public_reference,
        "created_at": row.created_at,
        "status": row.status,
        "status_label": label,
        "tone": tone,
        "customer": tracking.first_name(row.name) if by_reference
        else tracking.initials(row.name),
        "reason": "",
        "next": _demo_next(row, language),
    }


def _payment_item(payment, language):
    label, tone = _state(PAYMENT_STATES, payment.status, language)
    return {
        "kind": "subscription_payment",
        # The last characters only; whoever searched typed the whole id.
        "reference": f"…{payment.transfer_reference[-4:]}",
        "created_at": payment.created_at,
        "status": payment.status,
        "status_label": label,
        "tone": tone,
        "customer": tracking.initials(payment.company.name),
        "total_display": tracking.money_display(payment.amount, payment.currency, language),
        "reason": payment.rejection_reason if payment.status == "rejected" else "",
        "next": _pick(
            language,
            "نطابق التحويل مع كشف حسابنا عادةً في نفس اليوم، وتظهر النتيجة في صفحة الاشتراك.",
            "We match the transfer against our statement, usually the same day; the "
            "result also shows on your subscription page.",
        ) if payment.status == "pending" else "",
    }


def _since():
    return timezone.now() - timedelta(days=tracking.LOOKUP_DAYS)


def _registrations():
    from website.models import RegistrationRequest

    return RegistrationRequest.objects.filter(created_at__gte=_since()).order_by(
        "-created_at", "-id"
    )


def _demos():
    from website.models import PlatformLead

    return PlatformLead.objects.filter(created_at__gte=_since()).order_by("-created_at", "-id")


def _payments_by_transfer_reference(query):
    from sales.serializers import normalise_reference
    from subscriptions.models import SubscriptionPayment

    if "@" in str(query or ""):
        return []
    value = normalise_reference(query)
    if len(value) < TRANSFER_REFERENCE_MIN:
        return []
    return list(
        SubscriptionPayment.objects.filter(created_at__gte=_since(), transfer_reference=value)
        .select_related("company")
        .order_by("-created_at", "-id")[: tracking.LOOKUP_LIMIT]
    )


# ---------------------------------------------------------------- lookup

def _by_reference(value, language):
    """Items for an exact reference, or None when nothing carries it."""
    if value.startswith("W"):
        order = _orders().filter(reference__iexact=value).first()
        return [_order_item(order, language, "first")] if order else None
    rows = _registrations() if value.startswith("R") else _demos()
    row = rows.filter(public_reference__iexact=value).first()
    if row is None:
        return None
    if value.startswith("R"):
        return [_registration_item(row, language, True)]
    return [_demo_item(row, language, True)]


def _by_contact(kind, value, language):
    limit = tracking.LOOKUP_LIMIT
    if not value:
        return []
    if kind == "email":
        orders = _orders().filter(email__iexact=value)
        registrations = _registrations().filter(email__iexact=value)
        demos = _demos().filter(email__iexact=value)
    elif kind == "phone":
        orders = _orders().filter(lookup_phone=value)
        registrations = _registrations().filter(lookup_phone=value)
        demos = _demos().filter(lookup_phone=value)
    else:
        from django.db.models import Q

        orders = _orders().filter(lookup_name=value)
        registrations = _registrations().filter(
            Q(lookup_name=value) | Q(lookup_company=value)
        )
        demos = _demos().filter(lookup_name=value)
    return (
        [_order_item(order, language, "initials") for order in orders[:limit]]
        + [_registration_item(row, language, False) for row in registrations[:limit]]
        + [_demo_item(row, language, False) for row in demos[:limit]]
    )


def lookup(query, language):
    """(kind searched, items) for a visitor's search, newest first, at most
    LOOKUP_LIMIT. ``kind`` is for the count-only log."""
    found = tracking.classify(query, reference=REFERENCE)
    if found is None:
        return "none", []
    kind, value = found
    items = None
    if kind == "reference":
        items = _by_reference(value, language)
        if items is None:
            # "William" or "Rashida" look like references; a miss is a name.
            kind, value = "name", tracking.name_key(query)
    if items is None:
        items = _by_contact(kind, value, language)
    items += [_payment_item(p, language) for p in _payments_by_transfer_reference(query)]
    items.sort(key=lambda item: item["created_at"], reverse=True)
    return kind, items[: tracking.LOOKUP_LIMIT]


def log_lookup(kind, items):
    """Counts, never the query."""
    counts = {}
    for item in items:
        counts[item["kind"]] = counts.get(item["kind"], 0) + 1
    logger.info(
        "platform-track lookup kind=%s hits=%d %s", kind, len(items),
        " ".join(f"{key}={value}" for key, value in sorted(counts.items())),
    )
