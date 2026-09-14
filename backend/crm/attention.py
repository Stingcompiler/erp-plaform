"""Attention source for CRM: follow-ups that came due and are still open."""

from django.utils import timezone

from core.attention import TONE_INFO, register


@register("crm", "crm", TONE_INFO)
def follow_ups_due(user, since):
    """Open follow-ups whose due date arrived since the last look (up to
    today) — the ones that became actionable, not the whole backlog. A
    follow-up appears at the start of its due day, so a day already seen
    does not count again."""
    from crm.models import FollowUp

    today = timezone.localdate()
    return FollowUp.objects.filter(
        company_id=user.company_id,
        done=False,
        due_date__gt=since.date(),
        due_date__lte=today,
    ).count()
