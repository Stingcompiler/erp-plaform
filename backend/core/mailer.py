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
from html import escape

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, send_mail
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


def _paragraphs(lines):
    return "".join(
        f'<p style="margin:0 0 12px">{escape(line)}</p>' for line in lines if line
    )


def send_bilingual(*, subject_ar, subject_en, ar, en, recipient, link=None, primary=None):
    """One email that reads correctly for either audience: the Arabic block
    is right-to-left, the English block left-to-right, and whichever matches
    the reader's screen language comes first — in the subject too. A plain
    text twin carries the same words for clients that drop HTML.

    ``link`` is rendered once as a button between the two halves so nobody
    has to hunt for it inside a paragraph."""
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

    html_blocks = {
        "ar": '<div dir="rtl" lang="ar" style="text-align:right">'
              f'{_paragraphs(blocks["ar"])}</div>',
        "en": '<div dir="ltr" lang="en" style="text-align:left">'
              f'{_paragraphs(blocks["en"])}</div>',
    }
    labels = {"ar": "فتح الرابط", "en": "Open the link"}
    button = (
        f'<p style="margin:20px 0;text-align:center"><a href="{escape(link)}" '
        'style="display:inline-block;padding:12px 28px;background:#0f766e;color:#fff;'
        'border-radius:8px;text-decoration:none;font-weight:600">'
        f'{labels[order[0]]} · {labels[order[1]]}</a><br>'
        f'<a href="{escape(link)}" style="font-size:12px;color:#6b7280;word-break:break-all">'
        f'{escape(link)}</a></p>'
        if link else ""
    )
    html = (
        '<!doctype html><html><head><meta charset="utf-8"></head>'
        '<body style="margin:0;background:#f4f5f7;padding:24px">'
        '<div style="max-width:560px;margin:0 auto;background:#fff;border-radius:12px;'
        'padding:28px;font-family:-apple-system,Segoe UI,Tahoma,Arial,sans-serif;'
        'font-size:15px;line-height:1.7;color:#111">'
        f'<div style="font-weight:700;font-size:18px;margin-bottom:16px">{BRAND}</div>'
        f'{html_blocks[order[0]]}{button}'
        '<hr style="border:0;border-top:1px solid #e5e7eb;margin:20px 0">'
        f'{html_blocks[order[1]]}'
        '</div></body></html>'
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
