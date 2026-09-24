from datetime import datetime, time
from decimal import Decimal
import logging

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework.exceptions import ValidationError

from core.entitlements import resolve_entitlements
from config.deployment import get_deployment_config
from subscriptions.models import (
    LIMIT_KEYS,
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
    "devices": lambda company: company.devices.filter(is_active=True).count(),
}
assert set(LIMIT_RESOLVERS) == set(LIMIT_KEYS) - {"storage_mb"}
logger = logging.getLogger(__name__)


def addon_lines(subscription):
    """One line per add-on the company pays for: resource, units, unit price,
    amount — per billing cycle, in the plan's currency."""
    version = subscription.plan_version
    prices = version.addon_prices or {}
    lines = []
    for resource, units in (subscription.extra_limits or {}).items():
        units = int(units or 0)
        if units <= 0 or resource not in prices:
            continue
        unit_price = Decimal(str(prices[resource]))
        lines.append({
            "resource": resource, "units": units, "unit_price": str(unit_price),
            "amount": str((unit_price * units).quantize(Decimal("0.01"))),
        })
    return lines


def recurring_price(subscription):
    """What a renewal costs: the plan plus every add-on, per billing cycle."""
    total = Decimal(subscription.plan_version.price or 0)
    for line in addon_lines(subscription):
        total += Decimal(line["amount"])
    return total.quantize(Decimal("0.01"))


def usage_for(company, limits=None):
    """Each counted resource as {"used", "limit"}; limit None when the plan
    does not cap it. One place, so the owner's page and the platform's
    company list can never disagree."""
    if limits is None:
        limits = resolve_entitlements(company, apply_policy=False).limits
    return {
        resource: {
            "used": resolver(company),
            "limit": int(limits[resource]) if limits.get(resource) is not None else None,
        }
        for resource, resolver in LIMIT_RESOLVERS.items()
    }


def assert_capacity(company, resource, increment=1):
    decision = resolve_entitlements(company, apply_policy=False)
    maximum = decision.limits.get(resource)
    if maximum is None:
        return
    resolver = LIMIT_RESOLVERS.get(resource)
    if resolver and resolver(company) + increment > int(maximum):
        if get_deployment_config().entitlement_policy == "observe":
            logger.warning(
                "subscription_capacity_observe company=%s resource=%s "
                "current=%s increment=%s limit=%s",
                company.pk, resource, resolver(company), increment, maximum,
            )
            return
        raise ValidationError(
            {
                "code": "plan_limit_reached",
                "detail": _("The %(resource)s limit for the current plan has been reached.")
                % {"resource": resource},
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


def normalise_currency(value):
    """"sd", " SDG " and "SDG" are one currency (PlanVersion.save stores it
    upper-cased); comparing raw strings refused money that was fine."""
    return (value or "").strip().upper()


def period_end_at(company, day):
    """The last instant of ``day`` in the company's business zone.

    The zone must be the company's, not whatever zone the request happened
    to activate: a platform admin has no company, so granting under the
    admin's request ended paid periods at midnight UTC (02:59 in Khartoum)
    while the same invoice granted from the company's side ended at local
    midnight."""
    from core.timezone import company_zone

    return timezone.make_aware(datetime.combine(day, time.max), company_zone(company))


def _carried_grace(subscription, new_end):
    """The grace window after a period is extended.

    grace_ends_at is an absolute date set against the old boundary (the
    trial's or the last paid period's end). Left alone after a renewal it
    pointed into the past: the company lost its grace at the next lapse and
    the owner's "valid until" showed the old date. The same length of grace
    now follows the new end; a grace that did not extend a boundary is
    dropped."""
    grace = subscription.grace_ends_at
    if grace is None:
        return None
    boundaries = [subscription.period_ends_at]
    if subscription.status == Subscription.TRIALING:
        boundaries.append(subscription.trial_ends_at)
    if grace >= new_end:
        return grace
    base = max((b for b in boundaries if b is not None and b <= grace), default=None)
    return None if base is None else new_end + (grace - base)


def grant_paid_invoice_period(invoice, actor):
    """Grant one invoice period at most once, inside the payment transaction."""
    if invoice.entitlement_granted_at is not None:
        return False
    subscription = Subscription.objects.select_for_update().get(
        pk=invoice.subscription_id
    )
    now = timezone.now()
    period_end = period_end_at(invoice.company, invoice.period_end)
    previous_status = subscription.status
    fields = []
    if subscription.period_ends_at is None or period_end > subscription.period_ends_at:
        grace_end = _carried_grace(subscription, period_end)
        if grace_end != subscription.grace_ends_at:
            subscription.grace_ends_at = grace_end
            fields.append("grace_ends_at")
        subscription.period_ends_at = period_end
        fields.append("period_ends_at")
    # A manual suspension is a separate administrative decision and a payment
    # cannot silently remove it. Other non-operational commercial states may
    # return to active only when the paid period is still in the future.
    if (
        subscription.status in {
            Subscription.TRIALING,
            Subscription.GRACE,
            Subscription.READ_ONLY,
        }
        and period_end > now
    ):
        subscription.status = Subscription.ACTIVE
        fields.append("status")
    if fields:
        subscription.revision += 1
        fields.extend(["revision", "updated_at"])
        subscription.save(update_fields=fields)
    invoice.entitlement_granted_at = now
    invoice.save(update_fields=["entitlement_granted_at"])
    SubscriptionEvent.objects.create(
        subscription=subscription,
        event_type="invoice_period_granted",
        from_status=previous_status,
        to_status=subscription.status,
        actor=actor,
        metadata={
            "invoice_id": invoice.pk,
            "invoice_number": invoice.number,
            "period_end": period_end.isoformat(),
        },
    )
    return True


@transaction.atomic
def reject_payment(payment_id, actor, reason):
    """Close a pending payment without granting anything.

    A rejected payment keeps its proof and reason so the company can see why
    (typo in the reference, amount mismatch, unreadable receipt) and record a
    corrected one. Verified payments are never rejected here; that would need
    a reversal of the periods already granted.
    """
    payment = SubscriptionPayment.objects.select_for_update().get(pk=payment_id)
    if payment.status == SubscriptionPayment.REJECTED:
        return payment
    if payment.status != SubscriptionPayment.PENDING:
        raise ValidationError(_("Only pending payments can be rejected."))
    if not reason.strip():
        raise ValidationError({"reason": _("Give the company a reason for the rejection.")})
    payment.status = SubscriptionPayment.REJECTED
    payment.rejection_reason = reason.strip()
    payment.verified_by = actor
    payment.verified_at = timezone.now()
    payment.save(update_fields=["status", "rejection_reason", "verified_by", "verified_at"])
    return payment


@transaction.atomic
def verify_and_allocate_payment(payment_id, actor, allocations):
    payment = SubscriptionPayment.objects.select_for_update().get(pk=payment_id)
    if payment.status == SubscriptionPayment.VERIFIED:
        return payment
    if payment.status != SubscriptionPayment.PENDING:
        # A rejected payment was closed with a reason the company can see;
        # the company records a corrected one instead.
        raise ValidationError(_("Only a pending payment can be approved."))
    # Payment, then subscription, then invoices: the same order as
    # subscriptions.renewals.renew_with_payment, so two approvals for one
    # company queue instead of deadlocking.
    Subscription.objects.select_for_update().filter(company_id=payment.company_id).first()
    requested = sum(item["amount"] for item in allocations)
    if requested != payment.amount:
        raise ValidationError(_("Allocations must equal the full payment amount."))
    touched_invoices = []
    for item in allocations:
        invoice = SubscriptionInvoice.objects.select_for_update().get(
            pk=item["invoice_id"], company=payment.company
        )
        if invoice.status != SubscriptionInvoice.ISSUED:
            raise ValidationError(
                _("Invoice %(number)s is not open for payment.") % {"number": invoice.number}
            )
        if normalise_currency(invoice.currency) != normalise_currency(payment.currency):
            raise ValidationError(
                _("Invoice %(number)s uses a different currency.") % {"number": invoice.number}
            )
        allocated = (
            invoice.allocations.filter(
                payment__status=SubscriptionPayment.VERIFIED
            ).aggregate(total=Sum("amount"))["total"]
            or 0
        )
        if allocated + item["amount"] > invoice.amount:
            raise ValidationError(
                _("Allocation exceeds invoice %(number)s balance.") % {"number": invoice.number}
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
            grant_paid_invoice_period(invoice, actor)
            from subscriptions.plan_changes import apply_on_invoice_paid

            apply_on_invoice_paid(invoice, actor)
    return payment
