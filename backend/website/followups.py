"""Follow-ups on platform leads and registration requests.

The console records that a member reached out (call, WhatsApp, email) and
when to try again; the attention badge counts follow-ups that fell due
since the member last looked. Nothing here is visible to the prospect.
"""
from django.utils import timezone

CONTACT_CHANNELS = ("whatsapp", "call", "email")


def due_since(queryset, since, now=None):
    """Rows whose follow-up became due after `since` (and is still due)."""
    now = now or timezone.now()
    return queryset.filter(next_follow_up_at__gt=since, next_follow_up_at__lte=now)
