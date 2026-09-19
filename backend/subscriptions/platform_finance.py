"""The platform's money, in one read: what recurs, what was collected, what
is owed — overall, per plan, per month and per company.

Two rules keep the numbers honest. Only VERIFIED payments count as money:
a pending transfer is a claim, not cash. And nothing is converted between
currencies: a plan priced in SDG and one in USD are reported side by side,
never summed. MRR normalises yearly plans to a twelfth of their price and
counts subscriptions that are active or in grace (still entitled, still
expected to pay); trials are not revenue yet.
"""

import csv
from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.db.models import Sum
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core import platform_roles
from core.permissions import IsPlatformAdmin
from subscriptions.models import (
    PaymentAllocation,
    Subscription,
    SubscriptionEvent,
    SubscriptionInvoice,
    SubscriptionPayment,
)

RECURRING = {Subscription.ACTIVE, Subscription.GRACE}
TWOPLACES = Decimal("0.01")


def monthly_price(version):
    price = Decimal(version.price or 0)
    if version.billing_cycle == version.YEARLY:
        price = price / 12
    return price.quantize(TWOPLACES)


def month_start(value):
    return date(value.year, value.month, 1)


def add_months(value, n):
    month = value.month - 1 + n
    return date(value.year + month // 12, month % 12 + 1, 1)


def month_key(value):
    return f"{value.year:04d}-{value.month:02d}"


def money(value):
    return str(Decimal(value or 0).quantize(TWOPLACES))


def build_report(months=12):
    now = timezone.now()
    today = timezone.localdate()
    this_month = month_start(today)
    first_month = add_months(this_month, -(months - 1))
    window_start = timezone.make_aware(
        timezone.datetime.combine(first_month, timezone.datetime.min.time())
    )

    subscriptions = list(
        Subscription.objects.select_related("company", "plan_version__plan")
    )
    verified = SubscriptionPayment.objects.filter(status=SubscriptionPayment.VERIFIED)
    issued = SubscriptionInvoice.objects.filter(
        status__in=[SubscriptionInvoice.ISSUED, SubscriptionInvoice.PAID]
    ).select_related("subscription__plan_version__plan")

    # Verified money already applied to each invoice.
    allocated = defaultdict(Decimal)
    for row in (
        PaymentAllocation.objects.filter(payment__status=SubscriptionPayment.VERIFIED)
        .values("invoice_id").annotate(total=Sum("amount"))
    ):
        allocated[row["invoice_id"]] = row["total"] or Decimal(0)

    per_currency = defaultdict(lambda: {
        "mrr": Decimal(0), "collected_month": Decimal(0), "collected_window": Decimal(0),
        "collected_total": Decimal(0), "outstanding": Decimal(0), "overdue": Decimal(0),
        "by_plan": defaultdict(lambda: {
            "active": 0, "trialing": 0, "other": 0, "mrr": Decimal(0),
            "collected_window": Decimal(0), "outstanding": Decimal(0),
        }),
        "monthly": {
            month_key(add_months(first_month, i)): {
                "month": month_key(add_months(first_month, i)),
                "invoiced": Decimal(0), "collected": Decimal(0),
            } for i in range(months)
        },
    })

    plan_of_sub = {}
    for sub in subscriptions:
        version = sub.plan_version
        code = version.plan.code
        plan_of_sub[sub.pk] = (version.currency, code, version.plan.name)
        block = per_currency[version.currency]
        plan = block["by_plan"][code]
        plan["name"] = version.plan.name
        if sub.status in RECURRING:
            mrr = monthly_price(version)
            block["mrr"] += mrr
            plan["mrr"] += mrr
            plan["active"] += 1
        elif sub.status == Subscription.TRIALING:
            plan["trialing"] += 1
        else:
            plan["other"] += 1

    last_payment = {}
    for payment in verified.order_by("verified_at"):
        block = per_currency[payment.currency]
        block["collected_total"] += payment.amount
        when = timezone.localtime(payment.verified_at or payment.created_at)
        if when >= window_start:
            block["collected_window"] += payment.amount
            key = month_key(when.date())
            if key in block["monthly"]:
                block["monthly"][key]["collected"] += payment.amount
        if month_start(when.date()) == this_month:
            block["collected_month"] += payment.amount
        last_payment[payment.company_id] = when
        # Plan attribution follows the invoice the money settled.
        for alloc in payment.allocations.select_related(
            "invoice__subscription__plan_version__plan"
        ):
            if when >= window_start:
                _, code, _ = plan_of_sub.get(
                    alloc.invoice.subscription_id,
                    (payment.currency, alloc.invoice.subscription.plan_version.plan.code, ""),
                )
                block["by_plan"][code]["collected_window"] += alloc.amount

    outstanding_by_company = defaultdict(Decimal)
    for invoice in issued:
        block = per_currency[invoice.currency]
        issued_on = timezone.localtime(invoice.issued_at or invoice.created_at).date()
        if issued_on >= first_month:
            key = month_key(issued_on)
            if key in block["monthly"]:
                block["monthly"][key]["invoiced"] += invoice.amount
        if invoice.status == SubscriptionInvoice.ISSUED:
            balance = invoice.amount - allocated[invoice.pk]
            if balance > 0:
                block["outstanding"] += balance
                outstanding_by_company[invoice.company_id] += balance
                code = invoice.subscription.plan_version.plan.code
                block["by_plan"][code]["outstanding"] += balance
                if invoice.due_at < now:
                    block["overdue"] += balance

    # Trial → paid: of every subscription that was ever on trial, how many
    # went on to a recurring state. Read from the event log, not the current
    # status, so a company that later cancelled still counts as converted.
    ever_trialing = set(
        SubscriptionEvent.objects.filter(from_status=Subscription.TRIALING)
        .values_list("subscription_id", flat=True)
    ) | {s.pk for s in subscriptions if s.status == Subscription.TRIALING}
    converted = set(
        SubscriptionEvent.objects.filter(
            from_status=Subscription.TRIALING, to_status__in=RECURRING
        ).values_list("subscription_id", flat=True)
    )
    status_counts = defaultdict(int)
    for sub in subscriptions:
        status_counts[sub.status] += 1

    new_by_month = defaultdict(int)
    for sub in subscriptions:
        created = timezone.localtime(sub.created_at).date()
        if created >= first_month:
            new_by_month[month_key(created)] += 1
    churn_by_month = defaultdict(int)
    for event in SubscriptionEvent.objects.filter(
        to_status=Subscription.CANCELLED, created_at__gte=window_start
    ):
        churn_by_month[month_key(timezone.localtime(event.created_at).date())] += 1

    companies = []
    for sub in subscriptions:
        currency, code, name = plan_of_sub[sub.pk]
        companies.append({
            "company_id": sub.company_id,
            "company": sub.company.name,
            "plan": name,
            "plan_code": code,
            "currency": currency,
            "status": sub.status,
            "monthly_price": (
                money(monthly_price(sub.plan_version)) if sub.status in RECURRING else None
            ),
            "outstanding": money(outstanding_by_company[sub.company_id]),
            "last_payment_at": last_payment.get(sub.company_id),
            "period_ends_at": sub.period_ends_at,
            "trial_ends_at": sub.trial_ends_at,
        })
    companies.sort(key=lambda c: (-Decimal(c["outstanding"]), c["company"]))

    currencies = []
    for currency in sorted(per_currency):
        block = per_currency[currency]
        currencies.append({
            "currency": currency,
            "mrr": money(block["mrr"]),
            "arr": money(block["mrr"] * 12),
            "collected_month": money(block["collected_month"]),
            "collected_window": money(block["collected_window"]),
            "collected_total": money(block["collected_total"]),
            "outstanding": money(block["outstanding"]),
            "overdue": money(block["overdue"]),
            "by_plan": sorted(
                [
                    {"code": code, "name": plan.get("name", code), "active": plan["active"],
                     "trialing": plan["trialing"], "other": plan["other"],
                     "mrr": money(plan["mrr"]), "collected_window": money(plan["collected_window"]),
                     "outstanding": money(plan["outstanding"])}
                    for code, plan in block["by_plan"].items()
                ],
                key=lambda p: (-Decimal(p["mrr"]), p["name"]),
            ),
            "monthly": [
                {**row, "invoiced": money(row["invoiced"]), "collected": money(row["collected"])}
                for row in block["monthly"].values()
            ],
        })

    return {
        "generated_at": now,
        "months": months,
        "currencies": currencies,
        "statuses": dict(status_counts),
        "trial_conversion": {
            "ever_trialing": len(ever_trialing),
            "converted": len(converted),
            "rate": (round(len(converted) / len(ever_trialing), 3) if ever_trialing else None),
        },
        "monthly_subscriptions": [
            {"month": month_key(add_months(first_month, i)),
             "new": new_by_month[month_key(add_months(first_month, i))],
             "cancelled": churn_by_month[month_key(add_months(first_month, i))]}
            for i in range(months)
        ],
        "companies": companies,
    }


class PlatformFinanceView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    platform_view_capability = platform_roles.BILLING_VIEW
    platform_capability = platform_roles.BILLING_REVIEW
    entitlement_exempt = True

    def get(self, request):
        try:
            months = max(1, min(36, int(request.query_params.get("months", 12))))
        except (TypeError, ValueError):
            months = 12
        report = build_report(months)
        if request.query_params.get("format") == "csv":
            return self._csv(report)
        return Response(report)

    @staticmethod
    def _csv(report):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="vezano-subscriptions.csv"'
        response.write("﻿")  # Excel reads UTF-8 (and Arabic) only with the BOM
        writer = csv.writer(response)
        writer.writerow([
            "company", "plan", "currency", "status", "monthly_price", "outstanding",
            "last_payment_at", "period_ends_at", "trial_ends_at",
        ])
        for row in report["companies"]:
            writer.writerow([
                row["company"], row["plan"], row["currency"], row["status"],
                row["monthly_price"] or "", row["outstanding"],
                row["last_payment_at"].isoformat() if row["last_payment_at"] else "",
                row["period_ends_at"].isoformat() if row["period_ends_at"] else "",
                row["trial_ends_at"].isoformat() if row["trial_ends_at"] else "",
            ])
        return response
