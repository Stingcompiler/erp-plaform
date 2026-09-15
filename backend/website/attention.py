"""Attention sources for the Vezano platform team (module None = platform only)."""

from core import platform_roles
from core.attention import TONE_INFO, TONE_WARN, register


@register("platform-registrations", None, TONE_INFO, capability=platform_roles.REGISTRATIONS_VIEW)
def registrations_to_review(user, since):
    from website.models import RegistrationRequest

    return RegistrationRequest.objects.filter(
        status__in=[RegistrationRequest.SUBMITTED, RegistrationRequest.UNDER_REVIEW],
        created_at__gt=since,
    ).count()


@register("platform-leads", None, TONE_INFO, capability=platform_roles.LEADS_VIEW)
def new_demo_requests(user, since):
    from website.models import PlatformLead

    return PlatformLead.objects.filter(
        status=PlatformLead.STATUS_NEW, created_at__gt=since
    ).count()


@register("platform-subscriptions", None, TONE_WARN, capability=platform_roles.SUBSCRIPTIONS_VIEW)
def subscription_payments_to_verify(user, since):
    from subscriptions.models import SubscriptionPayment

    return SubscriptionPayment.objects.filter(
        status=SubscriptionPayment.PENDING, created_at__gt=since
    ).count()
