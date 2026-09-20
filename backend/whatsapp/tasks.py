"""Nightly housekeeping for the WhatsApp channel."""
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone


@shared_task
def prune_webhook_events():
    """Raw webhook bodies are for debugging a bad parse, not a record: drop
    them after WHATSAPP_EVENT_RETENTION_DAYS. Messages themselves stay."""
    from whatsapp.models import WhatsAppWebhookEvent

    days = max(1, int(getattr(settings, "WHATSAPP_EVENT_RETENTION_DAYS", 14)))
    cutoff = timezone.now() - timedelta(days=days)
    deleted, _ = WhatsAppWebhookEvent.objects.filter(received_at__lt=cutoff).delete()
    return {"deleted": deleted, "retention_days": days}
