"""Attention sources for the Vezano platform team (module None = platform only)."""

from core import platform_roles
from core.attention import TONE_INFO, TONE_WARN, register


@register("platform-registrations", None, TONE_INFO, capability=platform_roles.REGISTRATIONS_VIEW)
def registrations_to_review(user, since):
    """New requests plus follow-ups that fell due since the last look."""
    from website.followups import due_since
    from website.models import RegistrationRequest

    fresh = RegistrationRequest.objects.filter(
        status__in=[RegistrationRequest.SUBMITTED, RegistrationRequest.UNDER_REVIEW],
        created_at__gt=since,
    ).count()
    due = due_since(
        RegistrationRequest.objects.exclude(
            status__in=[
                RegistrationRequest.PROVISIONED, RegistrationRequest.REJECTED,
                RegistrationRequest.WITHDRAWN,
            ]
        ),
        since,
    ).count()
    return fresh + due


@register("platform-leads", None, TONE_INFO, capability=platform_roles.LEADS_VIEW)
def new_demo_requests(user, since):
    """New demo requests plus follow-ups that fell due since the last look."""
    from website.followups import due_since
    from website.models import PlatformLead

    fresh = PlatformLead.objects.filter(
        status=PlatformLead.STATUS_NEW, created_at__gt=since
    ).count()
    due = due_since(
        PlatformLead.objects.exclude(status=PlatformLead.STATUS_CLOSED), since
    ).count()
    return fresh + due


@register("platform-subscriptions", None, TONE_WARN, capability=platform_roles.SUBSCRIPTIONS_VIEW)
def subscription_payments_to_verify(user, since):
    from subscriptions.models import SubscriptionPayment

    from subscriptions.models import PlanChangeRequest

    payments = SubscriptionPayment.objects.filter(
        status=SubscriptionPayment.PENDING, created_at__gt=since
    ).count()
    changes = PlanChangeRequest.objects.filter(
        status=PlanChangeRequest.PENDING, created_at__gt=since
    ).count()
    return payments + changes
