"""Daily commercial scan for the platform team, run by Celery beat.

Trials ending within a week, paid periods that have lapsed, and grace
windows about to close. Logged once per day as a platform-level ActivityLog
row (company=None); the platform overview shows the same queues live.
"""

from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from core.activity import log_activity


@shared_task
def scan_subscription_expiries():
    from subscriptions.models import Subscription

    now = timezone.now()
    soon = now + timedelta(days=7)
    trials_ending = Subscription.objects.filter(
        status=Subscription.TRIALING, trial_ends_at__gte=now, trial_ends_at__lte=soon
    ).count()
    trials_lapsed = Subscription.objects.filter(
        status=Subscription.TRIALING, trial_ends_at__lt=now
    ).count()
    periods_lapsed = Subscription.objects.filter(
        status=Subscription.ACTIVE, period_ends_at__lt=now
    ).count()
    grace_closing = Subscription.objects.filter(
        status=Subscription.GRACE, grace_ends_at__gte=now, grace_ends_at__lte=soon
    ).count()
    from subscriptions.plan_changes import apply_due_downgrades

    payload = {
        "downgrades_applied": apply_due_downgrades(now),
        "trials_ending_7d": trials_ending,
        "trials_lapsed": trials_lapsed,
        "periods_lapsed": periods_lapsed,
        "grace_closing_7d": grace_closing,
    }
    if any(payload.values()):
        log_activity(action="scan", entity_type="SubscriptionExpiries", metadata=payload)
    return payload
