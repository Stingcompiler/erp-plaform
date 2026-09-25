"""Identity review (2026-09-25): an owner on a plan without the reports
module saw "4 reports failed" — every report endpoint answered
module_not_in_plan, but /me still listed all five report areas, so the
screen asked for each one and counted the refusals as failures."""

from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Role, User
from org.models import Company
from subscriptions.models import Plan, PlanVersion, Subscription


@override_settings(SUBSCRIPTION_POLICY="enforce")
class ReportAreasFollowThePlanTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        role = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        self.company = Company.objects.create(name="Alpha", currency="SDG")
        self.owner = User.objects.create_user(
            email="owner@alpha.test", password="Owner-passw0rd!x", company=self.company,
            role=role,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def subscribe(self, modules):
        plan = Plan.objects.create(code=f"p{len(modules)}", name="Plan")
        version = PlanVersion.objects.create(
            plan=plan, version=1, modules=modules, published_at=self.now
        )
        Subscription.objects.create(
            company=self.company, plan_version=version, status=Subscription.ACTIVE,
            starts_at=self.now, period_ends_at=self.now + timedelta(days=30),
        )

    def test_plan_without_reports_lists_no_report_areas(self):
        self.subscribe(["sales", "inventory", "purchasing"])
        me = self.client.get("/api/auth/me/").data
        self.assertEqual(me["report_areas"], [])
        self.assertEqual(me["entitlements"]["modules"], ["inventory", "purchasing", "sales"])
        self.assertEqual(me["currency"], "SDG")
        # …and the endpoints agree: the refusal is the plan, not the role.
        refused = self.client.get("/api/reports/sales-summary/")
        self.assertEqual(refused.status_code, 403)
        self.assertEqual(refused.data["code"], "module_not_in_plan")

    def test_plan_with_reports_keeps_every_owner_area(self):
        self.subscribe(["sales", "inventory", "reports"])
        me = self.client.get("/api/auth/me/").data
        self.assertEqual(
            me["report_areas"], ["finance", "hr", "inventory", "purchasing", "sales"]
        )
        self.assertEqual(self.client.get("/api/reports/sales-summary/").status_code, 200)
