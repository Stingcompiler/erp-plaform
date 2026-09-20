"""Sending through Meta's Graph API, best-effort.

Same contract as core/mailer.py: a send never raises into the caller and
never blocks the business action that triggered it. Every attempt leaves
a WhatsAppMessage row — accepted ones with Meta's id (the webhook then
moves them sent → delivered → read), failed ones with Meta's error — so
the settings screen can show what happened without reading logs.

Standard library only: one JSON POST, ten seconds, no retries here (Meta
queues on its side; a retry storm from a till is worse than a miss).
"""
import json
import logging
import urllib.error
import urllib.request
from uuid import uuid4

from django.conf import settings
from django.db import IntegrityError, transaction

from whatsapp.models import WhatsAppMessage, digits_only

logger = logging.getLogger(__name__)
GRAPH_VERSION = "v21.0"
TIMEOUT_SECONDS = 10


def graph_url(phone_number_id):
    base = getattr(settings, "WHATSAPP_GRAPH_BASE", "https://graph.facebook.com")
    return f"{base}/{GRAPH_VERSION}/{phone_number_id}/messages"


def _post_json(url, token, body, timeout=TIMEOUT_SECONDS):
    """Return (http_status, parsed_json). Network failures raise OSError."""
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return response.status, json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8") or "{}")
        except ValueError:
            payload = {}
        return exc.code, payload


def can_send(account):
    return bool(account and account.is_active and account.access_token)


def text_payload(to, text):
    return {
        "messaging_product": "whatsapp", "recipient_type": "individual",
        "to": to, "type": "text", "text": {"preview_url": False, "body": text},
    }


def template_payload(to, name, language, params):
    components = []
    if params:
        components.append({
            "type": "body",
            "parameters": [{"type": "text", "text": str(p)} for p in params],
        })
    return {
        "messaging_product": "whatsapp", "recipient_type": "individual",
        "to": to, "type": "template",
        "template": {"name": name, "language": {"code": language}, "components": components},
    }


def send(account, to_phone, payload, *, purpose="", customer=None, text=""):
    """POST one message. Returns the WhatsAppMessage row, or None when the
    account cannot send at all (no token / inactive / no phone)."""
    to = digits_only(to_phone)
    if not can_send(account) or len(to) < 8:
        return None
    row = WhatsAppMessage.objects.create(
        account=account, company=account.company, direction=WhatsAppMessage.OUTBOUND,
        wa_message_id=f"local:{uuid4().hex}", phone=to, customer=customer,
        message_type=payload.get("type", ""), text=text or "",
        status=WhatsAppMessage.QUEUED, raw={"purpose": purpose, "request": payload},
    )
    try:
        status, body = _post_json(graph_url(account.phone_number_id), account.access_token, payload)
    except (OSError, ValueError) as exc:
        logger.warning("WhatsApp send failed for %s: %s", account, exc)
        row.status = WhatsAppMessage.FAILED
        row.error_code = "network"
        row.error_title = str(exc)[:255]
        row.save(update_fields=["status", "error_code", "error_title", "updated_at"])
        return row
    messages = body.get("messages") or []
    if status < 300 and messages and messages[0].get("id"):
        row.raw = {**row.raw, "response": body}
        meta_id = str(messages[0]["id"])[:128]
        try:
            with transaction.atomic():
                row.wa_message_id = meta_id
                row.save(update_fields=["wa_message_id", "raw", "updated_at"])
        except IntegrityError:
            # Meta ids are unique; if one ever repeats, keep our local id
            # rather than lose the accepted send.
            row.wa_message_id = f"local:{uuid4().hex}"
            row.raw = {**row.raw, "duplicate_meta_id": meta_id}
            row.save(update_fields=["wa_message_id", "raw", "updated_at"])
        return row
    error = body.get("error") or {}
    row.status = WhatsAppMessage.FAILED
    row.error_code = str(error.get("code") or status)[:32]
    row.error_title = str(
        error.get("error_user_msg") or error.get("message") or f"HTTP {status}"
    )[:255]
    row.raw = {**row.raw, "response": body}
    row.save(update_fields=["status", "error_code", "error_title", "raw", "updated_at"])
    logger.warning("WhatsApp rejected a message for %s: %s", account, row.error_title)
    return row
