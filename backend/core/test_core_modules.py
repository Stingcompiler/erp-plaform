"""A plan that sells only some business modules must still let the owner
run the company: people, branches and settings are never plan-gated."""

from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Role, User
from org.models import Company
from subscriptions.models import Plan, PlanVersion, Subscription


@override_settings(SUBSCRIPTION_POLICY="enforce")
class CoreModulesAlwaysIncludedTests(TestCase):
    def setUp(self):
        now = timezone.now()
        owner_role = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        self.company = Company.objects.create(name="Alpha")
        self.owner = User.objects.create_user(
            email="owner@alpha.test", password="Owner-passw0rd!x", company=self.company,
            role=owner_role,
        )
        plan = Plan.objects.create(code="sales-only", name="Sales only")
        version = PlanVersion.objects.create(
            plan=plan, version=1, modules=["sales", "inventory"], published_at=now
        )
        Subscription.objects.create(
            company=self.company, plan_version=version, status=Subscription.ACTIVE,
            starts_at=now, period_ends_at=now + timedelta(days=30),
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def test_users_branches_and_settings_are_open_but_hr_is_not(self):
        self.assertEqual(self.client.get("/api/users/").status_code, 200)
        self.assertEqual(self.client.get("/api/branches/").status_code, 200)
        self.assertEqual(self.client.get("/api/company/profile/").status_code, 200)
        self.assertEqual(self.client.get("/api/website/page/").status_code, 200)
        hr = self.client.get("/api/employees/")
        self.assertEqual(hr.status_code, 403)
        self.assertEqual(hr.data["code"], "module_not_in_plan")
