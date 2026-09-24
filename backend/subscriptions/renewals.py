"""Renewing a subscription from a payment the company recorded.

A company pays first (cash at the office, a bank-app transfer) and records
the payment; the platform checks its statement and approves. Approval used
to need an issued invoice to allocate to, so a company that simply paid
left the platform with a disabled button and a separate manual step. Here
the invoice follows the money:

* open renewal invoices (issued, unpaid, not a plan change) are filled
  first, oldest period first;
* whatever is left buys whole billing cycles at the subscription's price
  (plan + add-ons, ``recurring_price``) — one invoice per cycle, each
  starting the day after the previous one ends;
* a remainder smaller than a cycle is allocated to the next cycle's
  invoice, which stays open with its balance showing to both sides; no
  period is granted for it until it is paid in full. Nothing is lost.

The first new cycle starts the day after the current access ends (the paid
period, or the trial while trialing), or today when access has already
lapsed — paying early never loses remaining days.

``plan_renewal`` is the dry run the platform page shows before approval;
``renew_with_payment`` performs it under a lock on the subscription and
refuses when the plan changed since the preview (a second payment from the
same company approved in between), so two payments never buy one period.
"""

import calendar
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from uuid import uuid4

from django.db import transaction
from django.db.models import Max, Sum
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework.exceptions import ValidationError

from core.timezone import company_zone
from subscriptions.models import (
    PlanVersion,
    Subscription,
    SubscriptionEvent,
    SubscriptionInvoice,
    SubscriptionPayment,
)
from subscriptions.services import (
    addon_lines,
    normalise_currency,
    period_end_at,
    recurring_price,
    verify_and_allocate_payment,
)

# A payment worth more than this many cycles is almost certainly a typo
# (an extra zero) and must be checked, not turned into years of invoices.
MAX_RENEWAL_CYCLES = 36
REACTIVATED_BY_PAYMENT = {Subscription.TRIALING, Subscription.GRACE, Subscription.READ_ONLY}


def add_months(day, months):
    """``day`` moved by whole months, clamped to the month's last day."""
    years, month_index = divmod(day.month - 1 + months, 12)
    year, month = day.year + years, month_index + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def cycle_months(version):
    return 12 if version.billing_cycle == PlanVersion.YEARLY else 1


def _local_date(company, moment):
    return timezone.localtime(moment, company_zone(company)).date()


def open_renewal_invoices(company):
    """Issued invoices a renewal payment may fill: not voided or paid, not a
    plan change (those switch the plan and are allocated by hand), and not
    already granted."""
    return SubscriptionInvoice.objects.filter(
        company=company,
        status=SubscriptionInvoice.ISSUED,
        plan_change__isnull=True,
        entitlement_granted_at__isnull=True,
    ).order_by("period_start", "pk")


def invoice_balance(invoice):
    paid = invoice.allocations.filter(
        payment__status=SubscriptionPayment.VERIFIED
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    return invoice.amount - paid


def current_access_end(subscription):
    """When what the company already has runs out: the paid period, or the
    trial while it is trialing."""
    ends = [subscription.period_ends_at]
    if subscription.status == Subscription.TRIALING:
        ends.append(subscription.trial_ends_at)
    return max((end for end in ends if end is not None), default=None)


def next_period_start(subscription, now=None):
    """First day of the next renewal period nobody has invoiced yet."""
    now = now or timezone.now()
    company = subscription.company
    end = current_access_end(subscription)
    if end is not None and end > now:
        start = _local_date(company, end) + timedelta(days=1)
    else:
        start = _local_date(company, now)
    last_open = open_renewal_invoices(company).aggregate(last=Max("period_end"))["last"]
    if last_open is not None and last_open >= start:
        start = last_open + timedelta(days=1)
    return start


def next_renewal(subscription, now=None):
    """What the company's next renewal costs and covers — shown to the owner
    before paying and used as the platform's invoice defaults."""
    version = subscription.plan_version
    start = next_period_start(subscription, now)
    months = cycle_months(version)
    open_balance = sum(
        (invoice_balance(invoice) for invoice in open_renewal_invoices(subscription.company)),
        Decimal("0"),
    )
    return {
        "amount": str(recurring_price(subscription)),
        "currency": normalise_currency(version.currency),
        "billing_cycle": version.billing_cycle,
        "period_start": start.isoformat(),
        "period_end": (add_months(start, months) - timedelta(days=1)).isoformat(),
        "open_balance": str(open_balance.quantize(Decimal("0.01"))),
    }


def _refused(reason, **extra):
    return {"ok": False, "reason": reason, "steps": [], "key": "", **extra}


def plan_renewal(payment, now=None):
    """What approving ``payment`` would do, without doing it."""
    now = now or timezone.now()
    if payment.status != SubscriptionPayment.PENDING:
        return _refused(_("Only a pending payment can be approved."))
    subscription = (
        Subscription.objects.select_related("plan_version__plan", "company")
        .filter(company_id=payment.company_id)
        .first()
    )
    if subscription is None:
        return _refused(_("This company has no subscription to renew."))
    company = subscription.company
    version = subscription.plan_version
    currency = normalise_currency(version.currency)
    if normalise_currency(payment.currency) != currency:
        return _refused(
            _(
                "Paid in %(paid)s but the subscription is billed in %(billed)s; it "
                "cannot renew it. Reject it and ask the company to pay in %(billed)s."
            ) % {"paid": payment.currency, "billed": currency},
            currency=currency,
        )
    price = recurring_price(subscription)
    if price <= 0:
        return _refused(
            _("This plan has no price, so there is nothing to renew with a payment."),
            currency=currency,
        )

    remaining = Decimal(payment.amount)
    steps = []
    for invoice in open_renewal_invoices(company):
        if normalise_currency(invoice.currency) != currency:
            continue
        balance = invoice_balance(invoice)
        if balance <= 0:
            continue
        take = min(balance, remaining)
        steps.append({
            "invoice_id": invoice.pk, "number": invoice.number,
            "period_start": invoice.period_start, "period_end": invoice.period_end,
            "amount": invoice.amount, "balance": balance, "allocate": take,
        })
        remaining -= take
        if not remaining:
            break
    first = next_period_start(subscription, now)
    months = cycle_months(version)
    cycle = 0
    while remaining > 0:
        if len(steps) >= MAX_RENEWAL_CYCLES:
            return _refused(
                _(
                    "This payment would cover more than %(count)s billing cycles. "
                    "Check the amount with the company before approving it."
                ) % {"count": MAX_RENEWAL_CYCLES},
                currency=currency,
            )
        take = min(price, remaining)
        steps.append({
            "invoice_id": None, "number": None,
            "period_start": add_months(first, months * cycle),
            "period_end": add_months(first, months * (cycle + 1)) - timedelta(days=1),
            "amount": price, "balance": price, "allocate": take,
        })
        remaining -= take
        cycle += 1

    access_until = subscription.period_ends_at
    status_after = subscription.status
    for step in steps:
        step["completes"] = step["allocate"] == step["balance"]
        step["balance_after"] = step["balance"] - step["allocate"]
        if not step["completes"]:
            continue
        end = period_end_at(company, step["period_end"])
        if access_until is None or end > access_until:
            access_until = end
        if status_after in REACTIVATED_BY_PAYMENT and end > now:
            status_after = Subscription.ACTIVE
    key = "|".join(
        f"{step['invoice_id'] or 'new'}:{step['period_start'].isoformat()}:{step['allocate']}"
        for step in steps
    )
    return {
        "ok": True, "reason": "", "currency": currency, "cycle_amount": price,
        "billing_cycle": version.billing_cycle, "steps": steps, "key": key,
        "access_until": access_until,
        "status_before": subscription.status, "status_after": status_after,
        "periods_granted": sum(1 for step in steps if step["completes"]),
        "other_pending": SubscriptionPayment.objects.filter(
            company_id=payment.company_id, status=SubscriptionPayment.PENDING,
        ).exclude(pk=payment.pk).count(),
    }


def renewal_as_json(plan):
    """``plan_renewal``'s result with dates and money as strings."""
    def money(value):
        return str(Decimal(value).quantize(Decimal("0.01")))

    data = {key: value for key, value in plan.items() if key != "steps"}
    if data.get("cycle_amount") is not None:
        data["cycle_amount"] = money(data["cycle_amount"])
    if data.get("access_until") is not None:
        data["access_until"] = data["access_until"].isoformat()
    data["steps"] = [
        {
            **step,
            "period_start": step["period_start"].isoformat(),
            "period_end": step["period_end"].isoformat(),
            "amount": money(step["amount"]),
            "balance": money(step["balance"]),
            "allocate": money(step["allocate"]),
            "balance_after": money(step["balance_after"]),
        }
        for step in plan["steps"]
    ]
    return data


def renewal_line_snapshot(subscription):
    version = subscription.plan_version
    lines = [{
        "kind": "renewal", "plan": version.plan.name, "plan_version": version.pk,
        "version": version.version, "billing_cycle": version.billing_cycle,
        "amount": str(Decimal(version.price or 0).quantize(Decimal("0.01"))),
    }]
    lines.extend({"kind": "addon", **line} for line in addon_lines(subscription))
    return lines


def issue_invoice(**fields):
    """Create an issued invoice numbered VSUB-000123 (its own id)."""
    invoice = SubscriptionInvoice.objects.create(
        number=f"PENDING-{uuid4().hex}", status=SubscriptionInvoice.ISSUED, **fields
    )
    invoice.number = f"VSUB-{invoice.pk:06d}"
    invoice.save(update_fields=["number"])
    return invoice


@transaction.atomic
def renew_with_payment(payment_id, actor, expected_key=None, now=None):
    """Approve ``payment`` as a renewal: issue the invoices it pays for,
    allocate it and grant every period it pays in full — one transaction.

    Replay-safe: a payment already verified is returned untouched.
    """
    now = now or timezone.now()
    payment = SubscriptionPayment.objects.select_for_update().get(pk=payment_id)
    if payment.status == SubscriptionPayment.VERIFIED:
        return payment, []
    # One company's renewals are decided one at a time: the second approval
    # waits here and then sees the period the first one granted.
    subscription = (
        Subscription.objects.select_for_update()
        .filter(company_id=payment.company_id)
        .first()
    )
    plan = plan_renewal(payment, now)
    if not plan["ok"]:
        raise ValidationError({"detail": plan["reason"]})
    if expected_key is not None and expected_key != plan["key"]:
        raise ValidationError({
            "code": "renewal_changed",
            "detail": _(
                "The renewal this payment buys has changed since the page was loaded "
                "(another payment from this company was approved). Check the new "
                "period and approve again."
            ),
        })
    subscription = Subscription.objects.select_related("plan_version__plan").get(
        pk=subscription.pk
    )
    allocations, issued = [], []
    for step in plan["steps"]:
        invoice_id = step["invoice_id"]
        if invoice_id is None:
            starts = timezone.make_aware(
                datetime.combine(step["period_start"], time.min),
                company_zone(subscription.company),
            )
            invoice = issue_invoice(
                company_id=payment.company_id, subscription=subscription,
                period_start=step["period_start"], period_end=step["period_end"],
                currency=plan["currency"], amount=step["amount"],
                due_at=max(now, starts), issued_at=now,
                line_snapshot=renewal_line_snapshot(subscription),
            )
            invoice_id = invoice.pk
            step["number"] = invoice.number
            issued.append(invoice.number)
        allocations.append({"invoice_id": invoice_id, "amount": step["allocate"]})
    verify_and_allocate_payment(payment.pk, actor, allocations)
    payment.refresh_from_db()
    SubscriptionEvent.objects.create(
        subscription=subscription,
        event_type="payment_renewed",
        from_status=plan["status_before"],
        to_status=Subscription.objects.values_list("status", flat=True).get(
            pk=subscription.pk
        ),
        actor=actor,
        metadata={
            "payment_id": payment.pk,
            "amount": str(payment.amount),
            "currency": payment.currency,
            "invoices_issued": issued,
            "periods_granted": plan["periods_granted"],
            "periods": [
                {
                    "invoice": step["number"],
                    "period_start": step["period_start"].isoformat(),
                    "period_end": step["period_end"].isoformat(),
                    "allocated": str(step["allocate"]),
                    "paid_in_full": step["completes"],
                }
                for step in plan["steps"]
            ],
        },
    )
    return payment, issued
