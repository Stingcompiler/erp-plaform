"""Parsing Meta's webhook body into messages and status updates.

Meta's shape (v21): ``entry[].changes[].value`` with ``metadata.phone_number_id``,
optional ``contacts[]``, ``messages[]`` (inbound) and ``statuses[]`` (our
outbound messages progressing). One body may carry several of each.
"""
import hashlib
import hmac
import logging
from datetime import datetime, timezone as dt_timezone

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from whatsapp.models import (
    WhatsAppAccount,
    WhatsAppMessage,
    WhatsAppWebhookEvent,
    digits_only,
)

logger = logging.getLogger(__name__)


def signature_is_valid(raw_body, header):
    """Meta signs the exact bytes with the app secret: ``sha256=<hex>``."""
    secret = getattr(settings, "WHATSAPP_APP_SECRET", "")
    if not secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header[len("sha256="):])


def _when(value):
    try:
        return datetime.fromtimestamp(int(value), tz=dt_timezone.utc)
    except (TypeError, ValueError):
        return None


def _text_of(message):
    kind = message.get("type", "")
    if kind == "text":
        return (message.get("text") or {}).get("body", "")
    if kind == "button":
        return (message.get("button") or {}).get("text", "")
    if kind == "interactive":
        inter = message.get("interactive") or {}
        chosen = inter.get("button_reply") or inter.get("list_reply") or {}
        return chosen.get("title", "")
    if kind in ("image", "document", "audio", "video", "sticker"):
        return (message.get(kind) or {}).get("caption", "")
    if kind == "location":
        loc = message.get("location") or {}
        return f"{loc.get('latitude')},{loc.get('longitude')}"
    return ""


def _contact_names(value):
    names = {}
    for contact in value.get("contacts") or []:
        wa_id = digits_only(contact.get("wa_id"))
        name = (contact.get("profile") or {}).get("name", "")
        if wa_id:
            names[wa_id] = str(name or "")[:120]
    return names


def _record_message(account, value, message, names):
    wa_id = str(message.get("id") or "")
    if not wa_id:
        return False
    phone = digits_only(message.get("from"))
    try:
        with transaction.atomic():
            WhatsAppMessage.objects.create(
                account=account, company=account.company,
                direction=WhatsAppMessage.INBOUND, wa_message_id=wa_id,
                phone=phone, contact_name=names.get(phone, ""),
                message_type=str(message.get("type") or "")[:32],
                text=_text_of(message), status=WhatsAppMessage.RECEIVED,
                wa_timestamp=_when(message.get("timestamp")), raw=message,
            )
    except IntegrityError:
        # Meta redelivered it; the first copy stands.
        return False
    return True


def _record_status(account, status):
    wa_id = str(status.get("id") or "")
    if not wa_id:
        return False
    new_status = str(status.get("status") or "").lower()
    if new_status not in WhatsAppMessage.STATUS_RANK:
        return False
    errors = status.get("errors") or []
    error = errors[0] if errors else {}
    row = WhatsAppMessage.objects.filter(wa_message_id=wa_id).first()
    if row is None:
        # A status for a message sent outside this system (Meta's own test
        # tool, a previous integration). Keep it so the timeline is honest.
        try:
            with transaction.atomic():
                WhatsAppMessage.objects.create(
                    account=account, company=account.company,
                    direction=WhatsAppMessage.OUTBOUND, wa_message_id=wa_id,
                    phone=digits_only(status.get("recipient_id")), status=new_status,
                    error_code=str(error.get("code") or "")[:32],
                    error_title=str(error.get("title") or "")[:255],
                    wa_timestamp=_when(status.get("timestamp")), raw=status,
                )
        except IntegrityError:
            return False
        return True
    rank = WhatsAppMessage.STATUS_RANK
    if rank.get(row.status, -1) >= rank[new_status] and new_status != WhatsAppMessage.FAILED:
        return False
    row.status = new_status
    if error:
        row.error_code = str(error.get("code") or "")[:32]
        row.error_title = str(error.get("title") or "")[:255]
    row.wa_timestamp = _when(status.get("timestamp")) or row.wa_timestamp
    row.save(update_fields=["status", "error_code", "error_title", "wa_timestamp", "updated_at"])
    return True


def process(payload):
    """Store what the body carries. Returns counters for the response/log."""
    counts = {"messages": 0, "statuses": 0, "unknown_numbers": 0}
    touched = set()
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            if change.get("field") not in (None, "messages"):
                continue
            value = change.get("value") or {}
            phone_number_id = str((value.get("metadata") or {}).get("phone_number_id") or "")
            account = WhatsAppAccount.objects.filter(
                phone_number_id=phone_number_id, is_active=True,
            ).select_related("company").first()
            if account is None:
                counts["unknown_numbers"] += 1
                logger.warning("WhatsApp event for unknown phone_number_id %r", phone_number_id)
                continue
            touched.add(account.pk)
            names = _contact_names(value)
            for message in value.get("messages") or []:
                if _record_message(account, value, message, names):
                    counts["messages"] += 1
            for status in value.get("statuses") or []:
                if _record_status(account, status):
                    counts["statuses"] += 1
    if touched:
        WhatsAppAccount.objects.filter(pk__in=touched).update(last_event_at=timezone.now())
    WhatsAppWebhookEvent.objects.create(
        account=WhatsAppAccount.objects.filter(pk__in=touched).first() if touched else None,
        payload=payload, **counts,
    )
    return counts
