from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from core.entitlements import resolve_entitlements
from subscriptions.models import (
    PaymentAllocation,
    Subscription,
    SubscriptionEvent,
    SubscriptionInvoice,
    SubscriptionPayment,
)


LIMIT_RESOLVERS = {
    "users": lambda company: company.users.filter(is_active=True).count(),
    "branches": lambda company: company.branches.filter(is_active=True).count(),
    "warehouses": lambda company: company.warehouses.filter(is_active=True).count(),
}


def assert_capacity(company, resource, increment=1):
    decision = resolve_entitlements(company)
    maximum = decision.limits.get(resource)
    if maximum is None:
        return
    resolver = LIMIT_RESOLVERS.get(resource)
    if resolver and resolver(company) + increment > int(maximum):
        raise ValidationError(
            {
                "code": "plan_limit_reached",
                "detail": f"The {resource} limit for the current plan has been reached.",
                "limit": int(maximum),
            }
        )


@transaction.atomic
def transition_subscription(subscription_id, target, actor, reason=""):
    subscription = Subscription.objects.select_for_update().get(pk=subscription_id)
    previous = subscription.status
    subscription.status = target
    subscription.suspended_reason = reason if target == Subscription.SUSPENDED else ""
    subscription.revision += 1
    subscription.save(
        update_fields=["status", "suspended_reason", "revision", "updated_at"]
    )
    SubscriptionEvent.objects.create(
        subscription=subscription,
        event_type="status_changed",
        from_status=previous,
        to_status=target,
        reason=reason,
        actor=actor,
    )
    return subscription, previous


@transaction.atomic
def configure_subscription(subscription_id, changes, actor, reason=""):
    """Apply a plan/term change atomically and preserve an auditable before/after event."""
    subscription = Subscription.objects.select_for_update().get(pk=subscription_id)
    previous_status = subscription.status
    previous_plan_id = subscription.plan_version_id
    for field, value in changes.items():
        setattr(subscription, field, value)
    subscription.revision += 1
    subscription.save()
    SubscriptionEvent.objects.create(
        subscription=subscription,
        event_type="configured",
        from_status=previous_status,
        to_status=subscription.status,
        reason=reason,
        actor=actor,
        metadata={
            "from_plan_version": previous_plan_id,
            "to_plan_version": subscription.plan_version_id,
        },
    )
    return subscription


@transaction.atomic
def verify_and_allocate_payment(payment_id, actor, allocations):
    payment = SubscriptionPayment.objects.select_for_update().get(pk=payment_id)
    if payment.status == SubscriptionPayment.VERIFIED:
        return payment
    requested = sum(item["amount"] for item in allocations)
    if requested != payment.amount:
        raise ValidationError("Allocations must equal the full payment amount.")
    touched_invoices = []
    for item in allocations:
        invoice = SubscriptionInvoice.objects.select_for_update().get(
            pk=item["invoice_id"], company=payment.company
        )
        if invoice.status != SubscriptionInvoice.ISSUED:
            raise ValidationError(f"Invoice {invoice.number} is not open for payment.")
        if invoice.currency != payment.currency:
            raise ValidationError(
                f"Invoice {invoice.number} uses a different currency."
            )
        allocated = (
            invoice.allocations.filter(
                payment__status=SubscriptionPayment.VERIFIED
            ).aggregate(total=Sum("amount"))["total"]
            or 0
        )
        if allocated + item["amount"] > invoice.amount:
            raise ValidationError(
                f"Allocation exceeds invoice {invoice.number} balance."
            )
        PaymentAllocation.objects.create(
            payment=payment, invoice=invoice, amount=item["amount"]
        )
        touched_invoices.append(invoice)
    payment.status = SubscriptionPayment.VERIFIED
    payment.verified_by = actor
    payment.verified_at = timezone.now()
    payment.save(update_fields=["status", "verified_by", "verified_at"])
    for invoice in touched_invoices:
        allocated = (
            invoice.allocations.filter(
                payment__status=SubscriptionPayment.VERIFIED
            ).aggregate(total=Sum("amount"))["total"]
            or 0
        )
        if allocated == invoice.amount:
            invoice.status = SubscriptionInvoice.PAID
            invoice.save(update_fields=["status"])
    return payment
