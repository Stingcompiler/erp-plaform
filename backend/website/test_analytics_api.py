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


class FunnelTests(TestCase):
    URL = "/api/platform/analytics/funnel/"

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(
            User.objects.create_superuser(email="root2@vezano.test", password="Root-passw0rd!")
        )

    def test_funnel_counts_each_stage_in_window(self):
        from subscriptions.models import Plan, PlanVersion, Subscription
        from org.models import Company
        from website.models import OwnerInvitation, PlatformLead, RegistrationRequest

        today = timezone.localdate()
        DailyPageStat.objects.create(
            date=today - timedelta(days=2), path="/", page_kind="marketing", visits=200, visitors=90
        )
        DailyPageStat.objects.create(  # public-site traffic is not funnel top
            date=today - timedelta(days=2), path="/s/x", page_kind="public_site",
            visits=50, visitors=20,
        )
        PageVisit.objects.create(path="/", page_kind="marketing", visitor_hash="live1")
        PlatformLead.objects.create(name="Lead", email="lead@example.test")
        registration = RegistrationRequest.objects.create(
            company_name="Acme", contact_name="A", email="a@example.test",
            status=RegistrationRequest.PROVISIONED,
        )
        RegistrationRequest.objects.create(
            company_name="Beta", contact_name="B", email="b@example.test",
        )
        owner = User.objects.create_user(email="owner2@acme.test", password="Owner-passw0rd!")
        OwnerInvitation.objects.create(
            token_hash="x" * 64, owner=owner, registration_request=registration,
            expires_at=timezone.now(), accepted_at=timezone.now(),
        )
        company = Company.objects.create(name="Acme Co")
        plan = Plan.objects.create(name="Basic", code="basic")
        version = PlanVersion.objects.create(plan=plan, version=1, published_at=timezone.now())
        Subscription.objects.create(
            company=company, plan_version=version, status=Subscription.ACTIVE,
            starts_at=timezone.now(),
        )

        response = self.client.get(self.URL, {"days": 30})
        self.assertEqual(response.status_code, 200)
        stages = {row["key"]: row for row in response.json()["stages"]}
        self.assertEqual(stages["visits"]["count"], 201)  # marketing only + live
        self.assertEqual(stages["leads"]["count"], 1)
        self.assertEqual(stages["registrations"]["count"], 2)
        self.assertEqual(stages["provisioned"]["count"], 1)
        self.assertEqual(stages["activated"]["count"], 1)
        self.assertEqual(stages["subscribed"]["count"], 1)
        self.assertIsNone(stages["visits"]["rate"])
        self.assertEqual(stages["provisioned"]["rate"], 50.0)

    def test_funnel_needs_platform_access(self):
        self.assertEqual(APIClient().get(self.URL).status_code, 401)


class CompanyVisitsTests(TestCase):
    URL = "/api/website/visits/"

    def _client_for_company(self, company):
        from accounts.models import Role

        role, _ = Role.objects.get_or_create(
            name="Business Owner", defaults={"scope_level": Role.SCOPE_BUSINESS}
        )
        user = User.objects.create_user(
            email=f"owner-{company.pk}@x.test", password="Owner-passw0rd!",
            company=company, role=role,
        )
        client = APIClient()
        client.force_authenticate(user)
        return client

    def test_company_sees_only_its_own_traffic(self):
        from org.models import Company

        mine, theirs = Company.objects.create(name="Mine"), Company.objects.create(name="Theirs")
        today = timezone.localdate()
        DailyPageStat.objects.create(
            date=today - timedelta(days=1), path="/s/mine", page_kind="public_site",
            company_id=mine.pk, visits=9, visitors=5,
        )
        DailyPageStat.objects.create(
            date=today - timedelta(days=1), path="/s/theirs", page_kind="public_site",
            company_id=theirs.pk, visits=100, visitors=60,
        )
        PageVisit.objects.create(
            path="/s/mine", page_kind="public_site", company_id=mine.pk, visitor_hash="v1"
        )

        response = self._client_for_company(mine).get(self.URL)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["visits"], 10)     # 9 rolled + 1 live, never theirs
        self.assertEqual(data["visitors"], 6)
        self.assertEqual(len(data["series"]), 30)
        self.assertEqual(data["series"][-1]["visits"], 1)

    def test_platform_admin_without_company_is_refused(self):
        client = APIClient()
        client.force_authenticate(
            User.objects.create_superuser(email="root3@vezano.test", password="Root-passw0rd!")
        )
        self.assertEqual(client.get(self.URL).status_code, 403)
