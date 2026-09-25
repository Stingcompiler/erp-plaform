"""The platform team's visits overview: KPIs for the public pages.

One read-only endpoint feeding /platform-analytics/. Finished days come
from DailyPageStat (the nightly rollup); today is computed live from the
PageVisit hot table so the page is never a day stale. Reads need
`platform.seo.view` — visits are marketing telemetry and belong to the
same people who run the SEO settings.
"""

from collections import Counter
from datetime import timedelta

from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core import platform_roles
from core.permissions import IsPlatformAdmin, RoleModuleAccess

WINDOWS = (7, 30, 90)


class PlatformAnalyticsOverview(APIView):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    platform_view_capability = platform_roles.SEO_VIEW
    platform_capability = platform_roles.SEO_VIEW
    entitlement_exempt = True

    def get(self, request):
        from website.models import DailyPageStat, PageVisit

        try:
            days = int(request.query_params.get("days", 30))
        except (TypeError, ValueError):
            days = 30
        if days not in WINDOWS:
            days = 30

        today = timezone.localdate()
        start = today - timedelta(days=days - 1)
        prev_start, prev_end = start - timedelta(days=days), start - timedelta(days=1)

        stats = DailyPageStat.objects.filter(date__gte=start, date__lte=today)
        live = list(
            PageVisit.objects.filter(created_at__date=today, is_bot=False).values(
                "path", "page_kind", "company_id", "referrer_host",
                "device", "language", "visitor_hash",
            )
        )

        # ---- daily series --------------------------------------------------
        by_day = {
            row["date"]: row
            for row in stats.values("date").annotate(v=Sum("visits"), u=Sum("visitors"))
        }
        series = []
        for offset in range(days):
            day = start + timedelta(days=offset)
            if day == today:
                visits = len(live)
                visitors = len({row["visitor_hash"] for row in live})
            else:
                row = by_day.get(day)
                visits, visitors = (row["v"], row["u"]) if row else (0, 0)
            series.append({"date": day.isoformat(), "visits": visits, "visitors": visitors})

        total_visits = sum(point["visits"] for point in series)
        total_visitors = sum(point["visitors"] for point in series)

        # ---- previous window, for the change badges ------------------------
        prev = DailyPageStat.objects.filter(date__gte=prev_start, date__lte=prev_end).aggregate(
            v=Sum("visits"), u=Sum("visitors")
        )
        prev_visits, prev_visitors = prev["v"] or 0, prev["u"] or 0

        # ---- breakdowns: rolled-up days + live today -----------------------
        pages, referrers, devices, languages = Counter(), Counter(), Counter(), Counter()
        page_kinds, company_pages = {}, Counter()
        for row in stats.values(
            "path", "page_kind", "company_id", "visits", "referrers", "devices", "languages"
        ):
            pages[row["path"]] += row["visits"]
            page_kinds[row["path"]] = row["page_kind"]
            referrers.update(row["referrers"])
            devices.update(row["devices"])
            languages.update(row["languages"])
            if row["page_kind"] == "public_site" and row["company_id"]:
                company_pages[(row["company_id"], row["path"])] += row["visits"]
        for row in live:
            pages[row["path"]] += 1
            page_kinds[row["path"]] = row["page_kind"]
            referrers[row["referrer_host"] or ""] += 1
            devices[row["device"] or ""] += 1
            languages[row["language"] or ""] += 1
            if row["page_kind"] == "public_site" and row["company_id"]:
                company_pages[(row["company_id"], row["path"])] += 1

        company_names = {}
        company_ids = {company_id for company_id, _ in company_pages}
        if company_ids:
            from org.models import Company

            company_names = dict(
                Company.objects.filter(pk__in=company_ids).values_list("pk", "name")
            )

        from django.db.models import Count as _Count
        from website.models import PublicOrder

        orders_by_company = dict(
            PublicOrder.objects.filter(created_at__date__gte=start)
            .values_list("company_id").annotate(n=_Count("id")).values_list("company_id", "n")
        )

        bot_visits = (
            (stats.aggregate(b=Sum("bot_visits"))["b"] or 0)
            + PageVisit.objects.filter(created_at__date=today, is_bot=True).count()
        )

        return Response({
            "days": days,
            "totals": {
                "visits": total_visits,
                "visitors": total_visitors,
                "pages_per_visitor": (
                    round(total_visits / total_visitors, 1) if total_visitors else 0
                ),
                "bot_visits": bot_visits,
                "previous_visits": prev_visits,
                "previous_visitors": prev_visitors,
            },
            "series": series,
            "top_pages": [
                {
                    "path": path,
                    "kind": page_kinds.get(path, ""),
                    "visits": count,
                    "share": round(count * 100 / total_visits, 1) if total_visits else 0,
                }
                for path, count in pages.most_common(10)
            ],
            "top_referrers": [
                {"host": host or "direct", "visits": count}
                for host, count in referrers.most_common(8)
            ],
            "devices": dict(devices),
            "languages": dict(languages),
            "top_company_pages": [
                {
                    "company_id": company_id,
                    "name": company_names.get(company_id, path),
                    "path": path,
                    "visits": count,
                    "orders": orders_by_company.get(company_id, 0),
                }
                for (company_id, path), count in company_pages.most_common(5)
            ],
            "public_orders": sum(orders_by_company.values()),
        })


class PlatformFunnelView(APIView):
    """The acquisition funnel: visit -> lead -> registration -> provisioned
    -> activated owner -> active subscription, over one window.

    Each stage counts what was *created* inside the window, so the numbers
    answer "of this period's interest, how far did it get?" — the question
    the platform team actually asks. Stages draw on different tables, so a
    later stage can exceed an earlier one in edge weeks (a registration
    provisioned this week from last week's lead); the page presents rates,
    not strict subsets.
    """

    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    platform_view_capability = platform_roles.SEO_VIEW
    platform_capability = platform_roles.SEO_VIEW
    entitlement_exempt = True

    def get(self, request):
        from subscriptions.models import Subscription
        from website.models import (
            DailyPageStat, OwnerInvitation, PageVisit, PlatformLead, RegistrationRequest,
        )

        try:
            days = int(request.query_params.get("days", 30))
        except (TypeError, ValueError):
            days = 30
        if days not in WINDOWS:
            days = 30
        today = timezone.localdate()
        start = today - timedelta(days=days - 1)
        window = {"created_at__date__gte": start}

        visits = (
            DailyPageStat.objects.filter(
                date__gte=start, page_kind="marketing"
            ).aggregate(v=Sum("visits"))["v"] or 0
        ) + PageVisit.objects.filter(
            created_at__date=today, is_bot=False, page_kind="marketing"
        ).count()

        registrations = RegistrationRequest.objects.filter(**window)
        stages = [
            {"key": "visits", "count": visits},
            {"key": "leads", "count": PlatformLead.objects.filter(**window).count()},
            {"key": "registrations", "count": registrations.count()},
            {
                "key": "provisioned",
                "count": registrations.filter(
                    status=RegistrationRequest.PROVISIONED
                ).count(),
            },
            {
                "key": "activated",
                "count": OwnerInvitation.objects.filter(
                    accepted_at__date__gte=start
                ).count(),
            },
            {
                "key": "subscribed",
                "count": Subscription.objects.filter(
                    created_at__date__gte=start, status=Subscription.ACTIVE
                ).count(),
            },
        ]
        for index, stage in enumerate(stages):
            previous = stages[index - 1]["count"] if index else None
            stage["rate"] = (
                round(stage["count"] * 100 / previous, 1)
                if previous else None
            )
        return Response({"days": days, "stages": stages})


class CompanyVisitsView(APIView):
    """A tenant's own public-page traffic: /s/<slug>/ visits for the
    signed-in user's company only.

    This is the sellable side of the analytics: the shop owner sees what
    their published page brings them. Company scoping is by the user's own
    company_id — no parameter is accepted, so there is nothing to guess.
    """

    permission_classes = [IsAuthenticated, RoleModuleAccess]
    rbac_module = "website"

    def get(self, request):
        from website.models import DailyPageStat, PageVisit

        company_id = getattr(request.user, "company_id", None)
        if company_id is None:
            return Response({"detail": _("A company workspace is required.")}, status=403)

        today = timezone.localdate()
        start = today - timedelta(days=29)
        rows = {
            row["date"]: row
            for row in DailyPageStat.objects.filter(
                company_id=company_id, date__gte=start
            ).values("date").annotate(v=Sum("visits"), u=Sum("visitors"))
        }
        live = PageVisit.objects.filter(
            company_id=company_id, created_at__date=today, is_bot=False
        )
        series = []
        for offset in range(30):
            day = start + timedelta(days=offset)
            if day == today:
                visits = live.count()
                visitors = live.values("visitor_hash").distinct().count()
            else:
                row = rows.get(day)
                visits, visitors = (row["v"], row["u"]) if row else (0, 0)
            series.append({"date": day.isoformat(), "visits": visits, "visitors": visitors})
        from website.models import PublicOrder

        orders = PublicOrder.objects.filter(company_id=company_id, created_at__date__gte=start)
        visits_total = sum(point["visits"] for point in series)
        orders_total = orders.count()
        return Response({
            "days": 30,
            "visits": visits_total,
            "visitors": sum(point["visitors"] for point in series),
            "series": series,
            # The page's job, in one number: how many visits became an order.
            "orders": orders_total,
            "orders_confirmed": orders.filter(status__in=PublicOrder.CONFIRMED_ONWARD).count(),
            "order_rate": round(orders_total * 100 / visits_total, 1) if visits_total else 0,
        })
