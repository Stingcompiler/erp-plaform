"""The visits overview endpoint: correct math, correct gatekeeping.

Yesterday comes from the rollup table, today from the hot table; the two
must combine into one seamless answer, and only platform members with the
SEO view capability may read any of it.
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from website.models import DailyPageStat, PageVisit


class AnalyticsOverviewTests(TestCase):
    URL = "/api/platform/analytics/overview/"

    def setUp(self):
        self.admin = User.objects.create_superuser(
            email="root@vezano.test", password="Root-passw0rd!"
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        today = timezone.localdate()
        DailyPageStat.objects.create(
            date=today - timedelta(days=1), path="/pricing", page_kind="marketing",
            visits=10, visitors=7, bot_visits=3,
            referrers={"google.com": 6, "": 4}, devices={"phone": 8, "desktop": 2},
            languages={"ar": 9, "en": 1},
        )
        DailyPageStat.objects.create(
            date=today - timedelta(days=1), path="/s/acme", page_kind="public_site",
            company_id=1, visits=5, visitors=4,
        )
        # The previous 30-day window, for the change badge.
        DailyPageStat.objects.create(
            date=today - timedelta(days=35), path="/pricing", page_kind="marketing",
            visits=4, visitors=2,
        )
        # Today, still un-rolled-up: two human views by one visitor, one bot.
        for is_bot, visitor in ((False, "aaa"), (False, "aaa"), (True, "bbb")):
            PageVisit.objects.create(
                path="/", page_kind="marketing", visitor_hash=visitor,
                is_bot=is_bot, device="desktop", language="ar",
            )

    def test_overview_combines_rollup_and_today(self):
        response = self.client.get(self.URL, {"days": 30})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["totals"]["visits"], 17)      # 10 + 5 + 2 live
        self.assertEqual(data["totals"]["visitors"], 12)    # 7 + 4 + 1 live
        self.assertEqual(data["totals"]["bot_visits"], 4)   # 3 rolled + 1 live
        self.assertEqual(data["totals"]["previous_visits"], 4)
        self.assertEqual(len(data["series"]), 30)
        self.assertEqual(data["series"][-1]["visits"], 2)   # today, live
        top = {row["path"]: row["visits"] for row in data["top_pages"]}
        self.assertEqual(top["/pricing"], 10)
        self.assertEqual(top["/"], 2)
        referrers = {row["host"]: row["visits"] for row in data["top_referrers"]}
        self.assertEqual(referrers["google.com"], 6)
        self.assertEqual(referrers["direct"], 6)  # 4 rolled + 2 live today
        self.assertEqual(data["devices"]["phone"], 8)
        self.assertEqual(data["top_company_pages"][0]["visits"], 5)

    def test_bad_window_falls_back_to_30(self):
        response = self.client.get(self.URL, {"days": "9999"})
        self.assertEqual(response.json()["days"], 30)

    def test_tenant_users_cannot_read(self):
        from org.models import Company

        company = Company.objects.create(name="Acme")
        user = User.objects.create_user(
            email="owner@acme.test", password="Owner-passw0rd!", company=company
        )
        client = APIClient()
        client.force_authenticate(user)
        self.assertEqual(client.get(self.URL).status_code, 403)

    def test_anonymous_cannot_read(self):
        self.assertEqual(APIClient().get(self.URL).status_code, 401)
