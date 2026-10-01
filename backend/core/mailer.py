"""The one place the backend sends email.

Email here is a best-effort side channel, never the system of record: every
flow that emails a link also hands the same link to the operator in the API
response, so a missing SMTP server or a bounced address can slow nobody
down. That is why ``send_transactional`` returns a boolean instead of
raising — callers report "email sent" or "deliver it yourself", and an SMTP
outage during provisioning must not roll back the provisioning.

Configuration lives in settings (EMAIL_HOST & friends); with no EMAIL_HOST
the backend is the console echo in DEBUG and a dummy sink in production,
and this module reports the send as not-sent without touching the backend.
"""

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, send_mail
from django.template.loader import render_to_string
from django.utils import translation

logger = logging.getLogger(__name__)

BRAND = "Vezano Pro · فيزانو برو"


def email_is_enabled():
    return bool(getattr(settings, "EMAIL_ENABLED", False))


def send_transactional(subject, body, recipient):
    """Send one plain-text email; True if handed to the backend, else False.

    Failures are logged, never raised: the caller always has a manual path
    for the same information.
    """
    if not recipient:
        return False
    if not email_is_enabled():
        logger.info("Email disabled; not sending %r to %s", subject, recipient)
        return False
    try:
        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [recipient],
            fail_silently=False,
        )
    except Exception:  # noqa: BLE001 - email must never break the caller
        logger.exception("Failed to send %r to %s", subject, recipient)
        return False
    return True


def primary_language():
    """The language the current request's screen is in ("ar" or "en"), so
    a bilingual email leads with the half its reader will actually read."""
    code = (translation.get_language() or settings.LANGUAGE_CODE or "ar")[:2]
    return code if code in ("ar", "en") else "ar"


# The header logo: a 2x PNG lockup on a white plate, made for email by
# frontend/scripts/email-logos.mjs (480x120) and served by the frontend.
LOGO_PATH = "/email/logo-{code}.png"
LOGO_WIDTH, LOGO_HEIGHT = 240, 60

FONTS = {
    "ar": "Tajawal, Readex Pro, Segoe UI, Geeza Pro, Noto Naskh Arabic, "
          "Noto Sans Arabic, Tahoma, Arial, sans-serif",
    "en": "Inter, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, "
          "Helvetica Neue, Arial, sans-serif",
}
LANGUAGE_COPY = {
    "ar": {
        "dir": "rtl",
        "align": "right",
        "logo_alt": "فيزانو برو",
        "button": "فتح الرابط",
        "label": "بالعربية",
        "link_hint": "إن لم يعمل الزر فانسخ هذا الرابط إلى المتصفح:",
        "tagline": "فيزانو برو — إدارة متكاملة لشركتك وفروعها",
        "automated": "رسالة آلية، لا تحتاج إلى رد.",
    },
    "en": {
        "dir": "ltr",
        "align": "left",
        "logo_alt": "Vezano Pro",
        "button": "Open the link",
        "label": "English",
        "link_hint": "If the button doesn't work, paste this link into your browser:",
        "tagline": "Vezano Pro — integrated management for companies and branches",
        "automated": "This is an automated message; no reply is needed.",
    },
}


def _asset_origin():
    """Where the email's images live: the app's public origin, else the
    product's canonical host, so a standalone install that has not set
    PUBLIC_APP_ORIGIN still shows the logo (from vezano.app)."""
    origin = (getattr(settings, "PUBLIC_APP_ORIGIN", "") or "").rstrip("/")
    return origin or f"https://{settings.VEZANO_CANONICAL_HOST}"


def render_bilingual_html(*, subject, blocks, order, link=None, preheader=None,
                          button_labels=None):
    """The HTML body of a bilingual email (templates/emails/bilingual.html).

    ``blocks`` maps "ar"/"en" to plain-text paragraphs, which the template
    autoescapes; ``order`` is (primary, secondary). The preheader (the
    inbox preview line) defaults to the first line of the primary block."""
    labels = button_labels or {}
    sides = []
    for code in order:
        copy = LANGUAGE_COPY[code]
        sides.append({
            **copy,
            "code": code,
            "font": FONTS[code],
            "paragraphs": [line for line in blocks[code] if line],
            "button": labels.get(code) or copy["button"],
        })
    primary, secondary = sides
    if preheader is None:
        preheader = primary["paragraphs"][0] if primary["paragraphs"] else ""
    host = settings.VEZANO_CANONICAL_HOST
    return render_to_string("emails/bilingual.html", {
        "subject": subject,
        "primary": primary,
        "secondary": secondary,
        "link": link,
        "preheader": preheader,
        "logo": {
            "url": _asset_origin() + LOGO_PATH.format(code=order[0]),
            "width": LOGO_WIDTH,
            "height": LOGO_HEIGHT,
            "alt": primary["logo_alt"],
        },
        "site_url": f"https://{host}",
        "site_label": host,
        "en_font": FONTS["en"],
    })


def send_bilingual(*, subject_ar, subject_en, ar, en, recipient, link=None, primary=None,
                   preheader=None, button_label_ar=None, button_label_en=None):
    """One email that reads correctly for either audience: the Arabic block
    is right-to-left, the English block left-to-right, and whichever matches
    the reader's screen language comes first — in the subject too. A plain
    text twin carries the same words for clients that drop HTML.

    ``link`` is rendered once as a button after the first half so nobody
    has to hunt for it inside a paragraph; ``button_label_ar``/``_en``
    replace its generic "Open the link" label. ``preheader`` overrides the
    inbox preview line (by default the first line of the first half)."""
    primary = primary or primary_language()
    order = ("ar", "en") if primary == "ar" else ("en", "ar")
    subjects = {"ar": subject_ar, "en": subject_en}
    blocks = {"ar": list(ar), "en": list(en)}
    subject = " | ".join(subjects[code] for code in order)

    text_parts = []
    for code in order:
        text_parts.append("\n".join(blocks[code]))
        if link and code == order[0]:
            text_parts.append(link)
    text_parts.append(f"— {BRAND}")
    text = "\n\n".join(text_parts)

    html = render_bilingual_html(
        subject=subject, blocks=blocks, order=order, link=link, preheader=preheader,
        button_labels={"ar": button_label_ar, "en": button_label_en},
    )

    if not recipient:
        return False
    if not email_is_enabled():
        logger.info("Email disabled; not sending %r to %s", subject, recipient)
        return False
    try:
        message = EmailMultiAlternatives(
            subject, text, settings.DEFAULT_FROM_EMAIL, [recipient]
        )
        message.attach_alternative(html, "text/html")
        message.send(fail_silently=False)
    except Exception:  # noqa: BLE001 - email must never break the caller
        logger.exception("Failed to send %r to %s", subject, recipient)
        return False
    return True


def activation_link(token, *, kind=None):
    """Absolute activation URL, or None when no public origin is configured
    (a standalone install that has not set PUBLIC_APP_ORIGIN)."""
    origin = (getattr(settings, "PUBLIC_APP_ORIGIN", "") or "").rstrip("/")
    if not origin:
        return None
    from urllib.parse import urlencode

    params = {"token": token}
    if kind:
        params = {"kind": kind, **params}
    return f"{origin}/activate-owner/?{urlencode(params)}"
