"""Moving a company between plans — the rules, in one place.

An UPGRADE (the target costs more per month) is invoiced for what is left
of the current period — (days left ÷ days in period) × (new price − old
price) — and the switch happens the moment that invoice is paid. Until
then the company keeps what it has. A target with the same price or less
is a DOWNGRADE: nothing to pay, the switch waits for the current period
to end, and it is refused outright while the company's usage exceeds the
target plan's limits (the owner must retire devices or users first, not
discover on Monday that nothing can be created).

ADD-ONS follow the same two shapes without leaving the plan: buying units
(a third till on a two-till plan) is invoiced pro rata at the plan's unit
price and applied when paid; giving units back waits for the period end
and is refused while they are still in use.

Both start as a request from the owner and need a platform decision; the
platform may also change a plan directly (configure_subscription), which
this module does not touch.
"""

from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
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


def same_currency(a, b):
    return (a or "").strip().upper() == (b or "").strip().upper()


def classify(from_version, to_version):
    if not same_currency(from_version.currency, to_version.currency):
        return PlanChangeRequest.SWITCH
    return (
        PlanChangeRequest.UPGRADE
        if monthly_price(to_version) > monthly_price(from_version)
        else PlanChangeRequest.DOWNGRADE
    )


def cycle_days(version):
    return 365 if version.billing_cycle == PlanVersion.YEARLY else 30


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


def period_fraction_left(subscription, version, now=None):
    """Share of the current period still ahead, 0 when it is over."""
    now = now or timezone.now()
    end = subscription.period_ends_at
    if end is None or end <= now:
        return Decimal(0)
    days = 365 if version.billing_cycle == PlanVersion.YEARLY else 30
    start = max(subscription.starts_at, end - timedelta(days=days))
    total = (end - start).total_seconds()
    left = (end - now).total_seconds()
    return Decimal(left / total).quantize(Decimal("0.0001")) if total > 0 else Decimal(0)


def proration(subscription, from_version, to_version, now=None):
    """Amount owed for the rest of the current period, and the fraction."""
    fraction = period_fraction_left(subscription, from_version, now)
    difference = Decimal(to_version.price or 0) - Decimal(from_version.price or 0)
    amount = (difference * fraction).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    return max(amount, Decimal("0.00")), fraction


def addon_delta_price(version, delta):
    """Full-cycle price of a units delta at the plan's add-on prices."""
    prices = version.addon_prices or {}
    total = Decimal(0)
    for resource, units in delta.items():
        total += Decimal(str(prices[resource])) * int(units)
    return total


def addon_proration(subscription, delta, now=None):
    fraction = period_fraction_left(subscription, subscription.plan_version, now)
    amount = (addon_delta_price(subscription.plan_version, delta) * fraction).quantize(
        TWOPLACES, rounding=ROUND_HALF_UP
    )
    return max(amount, Decimal("0.00")), fraction


def clean_delta(version, raw):
    """Validate {"devices": 2, "users": -1}: known, priced, non-zero ints."""
    prices = version.addon_prices or {}
    delta = {}
    for resource, units in (raw or {}).items():
        if resource not in prices:
            raise ValidationError(
                {
                    "extra_delta": _("%(resource)s cannot be added to this plan.")
                    % {"resource": resource}
                }
            )
        try:
            units = int(units)
        except (TypeError, ValueError):
            raise ValidationError({"extra_delta": _("Units must be whole numbers.")})
        if units:
            delta[resource] = units
    if not delta:
        raise ValidationError({"extra_delta": _("Say how many units to add or remove.")})
    if any(u > 0 for u in delta.values()) and any(u < 0 for u in delta.values()):
        raise ValidationError({"extra_delta": _("Add or remove units in one request, not both.")})
    return delta


def extra_after(subscription, delta):
    extra = dict(subscription.extra_limits or {})
    for resource, units in delta.items():
        extra[resource] = int(extra.get(resource, 0)) + units
        if extra[resource] < 0:
            raise ValidationError(
                {
                    "extra_delta": _("The company has no %(resource)s add-on to remove.")
                    % {"resource": resource}
                }
            )
    return {k: v for k, v in extra.items() if v}


def usage_over_extra(company, version, extra):
    """Resources used beyond plan limit + extra units."""
    over = {}
    for resource, maximum in (version.limits or {}).items():
        resolver = LIMIT_RESOLVERS.get(resource)
        if resolver is None or maximum is None:
            continue
        allowed = int(maximum) + int(extra.get(resource, 0))
        used = resolver(company)
        if used > allowed:
            over[resource] = {"used": used, "limit": allowed}
    return over


def open_request(company):
    return PlanChangeRequest.objects.filter(
        company=company, status__in=[PlanChangeRequest.PENDING, PlanChangeRequest.APPROVED]
    ).select_related("to_version__plan", "from_version__plan", "invoice").first()


@transaction.atomic
def request_change(company, to_version, actor, note=""):
    subscription = Subscription.objects.select_for_update().filter(company=company).first()
    if subscription is None:
        raise ValidationError({"detail": _("This company has no subscription to change.")})
    if to_version.published_at is None or not to_version.plan.is_active:
        raise ValidationError({"to_version": _("That plan is not available.")})
    if to_version.pk == subscription.plan_version_id:
        raise ValidationError({"to_version": _("The company is already on that plan.")})
    if open_request(company) is not None:
        raise ValidationError({"detail": _("A plan change is already waiting for a decision.")})
    kind = classify(subscription.plan_version, to_version)
    # A smaller plan (or one in another currency that may be smaller) must
    # still fit what the company already uses.
    if kind in (PlanChangeRequest.DOWNGRADE, PlanChangeRequest.SWITCH):
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
def request_addon(company, raw_delta, actor, note=""):
    subscription = Subscription.objects.select_for_update().filter(company=company).first()
    if subscription is None:
        raise ValidationError({"detail": _("This company has no subscription to change.")})
    if open_request(company) is not None:
        raise ValidationError({"detail": _("A plan change is already waiting for a decision.")})
    version = subscription.plan_version
    delta = clean_delta(version, raw_delta)
    adding = all(u > 0 for u in delta.values())
    target_extra = extra_after(subscription, delta)
    if not adding:
        over = usage_over_extra(company, version, target_extra)
        if over:
            raise UsageExceedsTarget(over)
    request = PlanChangeRequest.objects.create(
        company=company, subscription=subscription,
        from_version=version, to_version=version,
        kind=PlanChangeRequest.ADDON if adding else PlanChangeRequest.ADDON_REMOVE,
        extra_delta=delta, note=note, requested_by=actor,
    )
    SubscriptionEvent.objects.create(
        subscription=subscription, event_type="plan_change_requested", actor=actor,
        metadata={"request": request.pk, "kind": request.kind, "extra_delta": delta},
    )
    return request


@transaction.atomic
def cancel_request(request, actor):
    if request.status not in (PlanChangeRequest.PENDING, PlanChangeRequest.APPROVED):
        raise ValidationError({"detail": _("This request is already closed.")})
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
        raise ValidationError({"detail": _("Only a pending request can be approved.")})
    subscription = Subscription.objects.select_for_update().get(pk=request.subscription_id)
    now = timezone.now()
    request.status = PlanChangeRequest.APPROVED
    request.decided_by = actor
    request.decided_at = now
    request.decision_note = note
    if request.kind == PlanChangeRequest.SWITCH:
        # Full price for a fresh period in the new currency. Paying grants
        # that period (entitlement_granted_at stays empty) and switches the
        # plan through apply_on_invoice_paid.
        to_version = request.to_version
        invoice = SubscriptionInvoice.objects.create(
            company=request.company, subscription=subscription,
            number=f"PENDING-{uuid4().hex}", status=SubscriptionInvoice.ISSUED,
            period_start=now.date(),
            period_end=(now + timedelta(days=cycle_days(to_version))).date(),
            currency=to_version.currency, amount=Decimal(to_version.price),
            due_at=now + timedelta(days=7), issued_at=now,
            line_snapshot=[{
                "kind": request.kind,
                "from_plan": request.from_version.plan.name,
                "from_currency": request.from_version.currency,
                "to_plan": to_version.plan.name,
                "to_currency": to_version.currency,
                "billing_cycle": to_version.billing_cycle,
            }],
        )
        invoice.number = f"VSUB-{invoice.pk:06d}"
        invoice.save(update_fields=["number"])
        request.invoice = invoice
        request.save()
    elif request.kind in (PlanChangeRequest.UPGRADE, PlanChangeRequest.ADDON):
        if request.kind == PlanChangeRequest.ADDON:
            amount, fraction = addon_proration(subscription, request.extra_delta, now)
        else:
            amount, fraction = proration(
                subscription, request.from_version, request.to_version, now
            )
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
                    "kind": request.kind,
                    "from_plan": request.from_version.plan.name,
                    "to_plan": request.to_version.plan.name,
                    "extra_delta": request.extra_delta,
                    "fraction_of_period": str(fraction),
                    "difference": str(
                        addon_delta_price(request.to_version, request.extra_delta)
                        if request.kind == PlanChangeRequest.ADDON
                        else Decimal(request.to_version.price)
                        - Decimal(request.from_version.price)
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
        raise ValidationError({"detail": _("Only a pending request can be rejected.")})
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
    if request.kind in (PlanChangeRequest.ADDON, PlanChangeRequest.ADDON_REMOVE):
        subscription.extra_limits = extra_after(subscription, request.extra_delta)
    else:
        subscription.plan_version = request.to_version
    subscription.revision += 1
    subscription.save(update_fields=["plan_version", "extra_limits", "revision", "updated_at"])
    now = timezone.now()
    request.status = PlanChangeRequest.APPLIED
    request.applied_at = now
    request.save(update_fields=["status", "applied_at"])
    SubscriptionEvent.objects.create(
        subscription=subscription, event_type="plan_changed", actor=actor,
        metadata={
            "request": request.pk, "kind": request.kind,
            "from_plan_version": previous, "to_plan_version": request.to_version_id,
            "extra_delta": request.extra_delta, "extra_limits": subscription.extra_limits,
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
        status=PlanChangeRequest.APPROVED,
        kind__in=[PlanChangeRequest.DOWNGRADE, PlanChangeRequest.ADDON_REMOVE],
        apply_at__lte=now,
    )
    count = 0
    for request in due:
        apply_request(request)
        count += 1
    return count
