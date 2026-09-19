"""Moving a company between plans — the rules, in one place.

An UPGRADE (the target costs more per month) is invoiced for what is left
of the current period — (days left ÷ days in period) × (new price − old
price) — and the switch happens the moment that invoice is paid. Until
then the company keeps what it has. A target with the same price or less
is a DOWNGRADE: nothing to pay, the switch waits for the current period
to end, and it is refused outright while the company's usage exceeds the
target plan's limits (the owner must retire devices or users first, not
discover on Monday that nothing can be created).

Both start as a request from the owner and need a platform decision; the
platform may also change a plan directly (configure_subscription), which
this module does not touch.
"""

from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from subscriptions.models import (
    PlanChangeRequest,
    PlanVersion,
    Subscription,
    SubscriptionEvent,
    SubscriptionInvoice,
)
from subscriptions.services import LIMIT_RESOLVERS

TWOPLACES = Decimal("0.01")


class UsageExceedsTarget(Exception):
    """A downgrade the company does not fit into; ``over`` names what."""

    def __init__(self, over):
        super().__init__("usage exceeds target plan")
        self.over = over


def monthly_price(version):
    price = Decimal(version.price or 0)
    return price / 12 if version.billing_cycle == PlanVersion.YEARLY else price


def classify(from_version, to_version):
    return (
        PlanChangeRequest.UPGRADE
        if monthly_price(to_version) > monthly_price(from_version)
        else PlanChangeRequest.DOWNGRADE
    )


def usage_over_limits(company, version):
    """Resources the company already uses beyond what ``version`` allows."""
    over = {}
    for resource, maximum in (version.limits or {}).items():
        resolver = LIMIT_RESOLVERS.get(resource)
        if resolver is None or maximum is None:
            continue
        used = resolver(company)
        if used > int(maximum):
            over[resource] = {"used": used, "limit": int(maximum)}
    return over


def proration(subscription, from_version, to_version, now=None):
    """Amount owed for the rest of the current period, and the fraction."""
    now = now or timezone.now()
    end = subscription.period_ends_at
    if end is None or end <= now:
        return Decimal("0.00"), Decimal(0)
    days = 365 if from_version.billing_cycle == PlanVersion.YEARLY else 30
    start = max(subscription.starts_at, end - timedelta(days=days))
    total = (end - start).total_seconds()
    left = (end - now).total_seconds()
    fraction = Decimal(left / total).quantize(Decimal("0.0001")) if total > 0 else Decimal(0)
    difference = Decimal(to_version.price or 0) - Decimal(from_version.price or 0)
    amount = (difference * fraction).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    return max(amount, Decimal("0.00")), fraction


def open_request(company):
    return PlanChangeRequest.objects.filter(
        company=company, status__in=[PlanChangeRequest.PENDING, PlanChangeRequest.APPROVED]
    ).select_related("to_version__plan", "from_version__plan", "invoice").first()


@transaction.atomic
def request_change(company, to_version, actor, note=""):
    subscription = Subscription.objects.select_for_update().filter(company=company).first()
    if subscription is None:
        raise ValidationError({"detail": "This company has no subscription to change."})
    if to_version.published_at is None or not to_version.plan.is_active:
        raise ValidationError({"to_version": "That plan is not available."})
    if to_version.pk == subscription.plan_version_id:
        raise ValidationError({"to_version": "The company is already on that plan."})
    if to_version.currency != subscription.plan_version.currency:
        raise ValidationError(
            {"to_version": "The new plan must be priced in the same currency."}
        )
    if open_request(company) is not None:
        raise ValidationError({"detail": "A plan change is already waiting for a decision."})
    kind = classify(subscription.plan_version, to_version)
    if kind == PlanChangeRequest.DOWNGRADE:
        over = usage_over_limits(company, to_version)
        if over:
            raise UsageExceedsTarget(over)
    request = PlanChangeRequest.objects.create(
        company=company, subscription=subscription,
        from_version=subscription.plan_version, to_version=to_version,
        kind=kind, note=note, requested_by=actor,
    )
    SubscriptionEvent.objects.create(
        subscription=subscription, event_type="plan_change_requested", actor=actor,
        metadata={"request": request.pk, "kind": kind, "to_plan_version": to_version.pk},
    )
    return request


@transaction.atomic
def cancel_request(request, actor):
    if request.status not in (PlanChangeRequest.PENDING, PlanChangeRequest.APPROVED):
        raise ValidationError({"detail": "This request is already closed."})
    if request.invoice_id and request.invoice.status == SubscriptionInvoice.ISSUED:
        request.invoice.status = SubscriptionInvoice.VOID
        request.invoice.save(update_fields=["status"])
    request.status = PlanChangeRequest.CANCELLED
    request.decided_at = timezone.now()
    request.save(update_fields=["status", "decided_at"])
    SubscriptionEvent.objects.create(
        subscription=request.subscription, event_type="plan_change_cancelled",
        actor=actor, metadata={"request": request.pk},
    )
    return request


@transaction.atomic
def approve_request(request, actor, note=""):
    request = PlanChangeRequest.objects.select_for_update().get(pk=request.pk)
    if request.status != PlanChangeRequest.PENDING:
        raise ValidationError({"detail": "Only a pending request can be approved."})
    subscription = Subscription.objects.select_for_update().get(pk=request.subscription_id)
    now = timezone.now()
    request.status = PlanChangeRequest.APPROVED
    request.decided_by = actor
    request.decided_at = now
    request.decision_note = note
    if request.kind == PlanChangeRequest.UPGRADE:
        amount, fraction = proration(subscription, request.from_version, request.to_version, now)
        if amount > 0:
            period_end = (subscription.period_ends_at or now).date()
            invoice = SubscriptionInvoice.objects.create(
                company=request.company, subscription=subscription,
                number=f"PENDING-{uuid4().hex}", status=SubscriptionInvoice.ISSUED,
                period_start=now.date(), period_end=period_end,
                currency=request.to_version.currency, amount=amount,
                due_at=now + timedelta(days=7), issued_at=now,
                # This period is already granted; paying must switch the plan,
                # not extend the term, so it is marked granted from the start.
                entitlement_granted_at=now,
                line_snapshot=[{
                    "kind": "plan_change",
                    "from_plan": request.from_version.plan.name,
                    "to_plan": request.to_version.plan.name,
                    "fraction_of_period": str(fraction),
                    "difference": str(
                        Decimal(request.to_version.price) - Decimal(request.from_version.price)
                    ),
                }],
            )
            invoice.number = f"VSUB-{invoice.pk:06d}"
            invoice.save(update_fields=["number"])
            request.invoice = invoice
            request.save()
        else:
            # Nothing left to pay this period (or no period at all): switch now.
            request.save()
            apply_request(request, actor)
            return request
    else:
        request.apply_at = subscription.period_ends_at or now
        request.save()
        if request.apply_at <= now:
            apply_request(request, actor)
            return request
    SubscriptionEvent.objects.create(
        subscription=subscription, event_type="plan_change_approved", actor=actor,
        reason=note, metadata={"request": request.pk, "invoice": request.invoice_id},
    )
    return request


@transaction.atomic
def reject_request(request, actor, note=""):
    request = PlanChangeRequest.objects.select_for_update().get(pk=request.pk)
    if request.status != PlanChangeRequest.PENDING:
        raise ValidationError({"detail": "Only a pending request can be rejected."})
    request.status = PlanChangeRequest.REJECTED
    request.decided_by = actor
    request.decided_at = timezone.now()
    request.decision_note = note
    request.save()
    SubscriptionEvent.objects.create(
        subscription=request.subscription, event_type="plan_change_rejected",
        actor=actor, reason=note, metadata={"request": request.pk},
    )
    return request


@transaction.atomic
def apply_request(request, actor=None):
    """Perform the switch. Idempotent: an applied request is left alone."""
    request = PlanChangeRequest.objects.select_for_update().get(pk=request.pk)
    if request.status == PlanChangeRequest.APPLIED:
        return request
    subscription = Subscription.objects.select_for_update().get(pk=request.subscription_id)
    previous = subscription.plan_version_id
    subscription.plan_version = request.to_version
    subscription.revision += 1
    subscription.save(update_fields=["plan_version", "revision", "updated_at"])
    now = timezone.now()
    request.status = PlanChangeRequest.APPLIED
    request.applied_at = now
    request.save(update_fields=["status", "applied_at"])
    SubscriptionEvent.objects.create(
        subscription=subscription, event_type="plan_changed", actor=actor,
        metadata={
            "request": request.pk, "kind": request.kind,
            "from_plan_version": previous, "to_plan_version": request.to_version_id,
        },
    )
    return request


def apply_on_invoice_paid(invoice, actor):
    """Called from payment verification: a paid upgrade invoice switches the plan."""
    request = getattr(invoice, "plan_change", None)
    if request is not None and request.status == PlanChangeRequest.APPROVED:
        apply_request(request, actor)


def apply_due_downgrades(now=None):
    """Daily: downgrades whose period has ended."""
    now = now or timezone.now()
    due = PlanChangeRequest.objects.filter(
        status=PlanChangeRequest.APPROVED, kind=PlanChangeRequest.DOWNGRADE, apply_at__lte=now
    )
    count = 0
    for request in due:
        apply_request(request)
        count += 1
    return count
