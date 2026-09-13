from datetime import timedelta

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import Role, User
from core.entitlements import resolve_entitlements
from inventory.models import Warehouse
from org.models import Branch, Company
from subscriptions.models import Plan, PlanVersion, Subscription


@override_settings(SUBSCRIPTION_POLICY="enforce", VEZANO_DEPLOYMENT_MODE="saas")
class CapacityReactivationTests(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Capacity")
        role = Role.objects.create(name="Business Owner", scope_level="business")
        self.owner = User.objects.create_user(
            email="owner@capacity.test", company=self.company, role=role,
        )
        self.client.force_authenticate(self.owner)
        branch = Branch.objects.create(company=self.company, name="Main")
        Warehouse.objects.create(company=self.company, branch=branch, name="Main")
        self.targets = [
            ("users", User.objects.create_user(
                email="inactive@capacity.test", company=self.company,
                role=role, is_active=False,
            )),
            ("branches", Branch.objects.create(
                company=self.company, name="Inactive", is_active=False,
            )),
            ("warehouses", Warehouse.objects.create(
                company=self.company, branch=branch, name="Inactive", is_active=False,
            )),
        ]
        plan = Plan.objects.create(code="capacity", name="Capacity")
        version = PlanVersion.objects.create(
            plan=plan, version=1, modules=["*"],
            limits={"users": 1, "branches": 1, "warehouses": 1},
            published_at=timezone.now(),
        )
        self.subscription = Subscription.objects.create(
            company=self.company, plan_version=version, status="active",
            starts_at=timezone.now() - timedelta(days=1),
            period_ends_at=timezone.now() + timedelta(days=1),
        )

    def test_all_reactivation_routes_enforce_capacity(self):
        for resource, target in self.targets:
            for action in ("patch", "unarchive"):
                with self.subTest(resource=resource, action=action):
                    url = f"/api/{resource}/{target.pk}/"
                    response = (
                        self.client.patch(url, {"is_active": True}, format="json")
                        if action == "patch"
                        else self.client.post(url + "unarchive/")
                    )
                    self.assertEqual(response.status_code, 400, response.data)
                    target.refresh_from_db()
                    self.assertFalse(target.is_active)

    @override_settings(SUBSCRIPTION_POLICY="observe")
    def test_observe_logs_but_allows_reactivation(self):
        for resource, target in self.targets:
            with self.assertLogs("subscriptions.services", level="WARNING") as logs:
                response = self.client.post(f"/api/{resource}/{target.pk}/unarchive/")
            self.assertEqual(response.status_code, 200, response.data)
            self.assertIn(f"resource={resource}", logs.output[0])
            target.refresh_from_db()
            self.assertTrue(target.is_active)
        self.assertTrue(resolve_entitlements(self.company).allow_writes)
        self.assertEqual(resolve_entitlements(self.company).limits, {})

    def test_grace_uses_its_own_deadline(self):
        now = timezone.now()
        self.subscription.status = "grace"
        self.subscription.period_ends_at = None
        for end, expected in [(now - timedelta(seconds=1), False),
                              (now, False), (None, False),
                              (now + timedelta(seconds=1), True)]:
            self.subscription.grace_ends_at = end
            self.subscription.save()
            company = Company.objects.get(pk=self.company.pk)
            self.assertEqual(resolve_entitlements(company, now).allow_writes, expected)

    @override_settings(SUBSCRIPTION_POLICY="disabled")
    def test_disabled_preserves_existing_access(self):
        resource, target = self.targets[0]
        response = self.client.patch(
            f"/api/{resource}/{target.pk}/", {"is_active": True}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)

    def test_reactivation_with_available_capacity_succeeds(self):
        Branch.objects.filter(company=self.company, is_active=True).update(is_active=False)
        resource, target = self.targets[1]
        response = self.client.patch(
            f"/api/{resource}/{target.pk}/", {"is_active": True}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
