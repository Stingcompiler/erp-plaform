from datetime import timedelta
from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Role, User
from org.models import Branch, Company
from subscriptions.models import (
    Plan,
    PlanVersion,
    Subscription,
    SubscriptionEvent,
    SubscriptionPayment,
)


class SubscriptionAccessTests(APITestCase):
    def setUp(self):
        self.owner_role = Role.objects.create(
            name="Business Owner", scope_level=Role.SCOPE_BUSINESS
        )
        self.sales_role = Role.objects.create(
            name="Sales Officer", scope_level=Role.SCOPE_BRANCH
        )
        self.company = Company.objects.create(name="Subscribed Co")
        self.other_company = Company.objects.create(name="Other Co")
        self.owner = User.objects.create_user(
            email="owner@sub.test",
            password="long-password",
            company=self.company,
            role=self.owner_role,
        )
        self.sales = User.objects.create_user(
            email="sales@sub.test",
            password="long-password",
            company=self.company,
            role=self.sales_role,
        )
        self.plan = Plan.objects.create(code="business", name="Business")
        self.version = PlanVersion.objects.create(
            plan=self.plan,
            version=1,
            modules=["*"],
            limits={"branches": 1},
            published_at=timezone.now(),
        )
        self.subscription = Subscription.objects.create(
            company=self.company,
            plan_version=self.version,
            status=Subscription.ACTIVE,
            starts_at=timezone.now(),
            period_ends_at=timezone.now() + timedelta(days=30),
        )

    def test_only_owner_can_read_company_subscription(self):
        self.client.force_authenticate(self.owner)
        response = self.client.get(reverse("company-subscription"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["subscription"]["company"], self.company.pk)

        self.client.force_authenticate(self.sales)
        response = self.client.get(reverse("company-subscription"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_payment_list_is_tenant_scoped_and_replay_safe(self):
        SubscriptionPayment.objects.create(
            company=self.other_company,
            amount=10,
            currency="USD",
            method="cash",
            recorded_by=self.owner,
        )
        self.client.force_authenticate(self.owner)
        payload = {
            "amount": "12.00",
            "currency": "USD",
            "method": "cash",
            "client_uuid": "fcf86a22-fbb4-43d2-8e40-dae995fce672",
        }
        first = self.client.post(reverse("subscription-payment-list"), payload)
        second = self.client.post(reverse("subscription-payment-list"), payload)
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(
            SubscriptionPayment.objects.filter(company=self.company).count(), 1
        )
        listed = self.client.get(reverse("subscription-payment-list"))
        self.assertEqual(listed.data["count"], 1)

    @override_settings(SUBSCRIPTION_POLICY="enforce")
    def test_read_only_subscription_blocks_business_writes_but_not_reads(self):
        self.subscription.status = Subscription.READ_ONLY
        self.subscription.save(update_fields=["status"])
        self.client.force_authenticate(self.owner)
        self.assertEqual(
            self.client.get(reverse("branch-list")).status_code, status.HTTP_200_OK
        )
        response = self.client.post(reverse("branch-list"), {"name": "Blocked"})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @override_settings(SUBSCRIPTION_POLICY="observe")
    def test_observe_mode_never_blocks_existing_flow(self):
        self.subscription.status = Subscription.READ_ONLY
        self.subscription.save(update_fields=["status"])
        self.client.force_authenticate(self.owner)
        response = self.client.post(reverse("branch-list"), {"name": "Observed"})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    @override_settings(SUBSCRIPTION_POLICY="observe")
    def test_observe_mode_does_not_block_unprovisioned_company(self):
        company = Company.objects.create(name="Observation Co")
        owner = User.objects.create_user(
            email="observe@test.local",
            password="long-password",
            company=company,
            role=self.owner_role,
        )
        self.client.force_authenticate(owner)
        response = self.client.post(reverse("branch-list"), {"name": "Main"})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    @override_settings(SUBSCRIPTION_POLICY="enforce")
    def test_plan_limit_prevents_second_branch(self):
        Branch.objects.create(company=self.company, name="Main")
        self.client.force_authenticate(self.owner)
        response = self.client.post(reverse("branch-list"), {"name": "Second"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "plan_limit_reached")

    def test_platform_transition_is_audited_as_subscription_event(self):
        admin = User.objects.create_superuser(
            email="platform@test.local", password="long-password"
        )
        self.client.force_authenticate(admin)
        response = self.client.post(
            reverse("platform-subscription-transition", args=[self.subscription.pk]),
            {"status": "suspended", "reason": "Manual review"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        event = SubscriptionEvent.objects.get(subscription=self.subscription)
        self.assertEqual((event.from_status, event.to_status), ("active", "suspended"))

    def test_platform_can_assign_a_published_plan_and_period_atomically(self):
        admin = User.objects.create_superuser(
            email="configure@test.local", password="long-password"
        )
        replacement_plan = Plan.objects.create(code="growth", name="Growth")
        replacement = PlanVersion.objects.create(
            plan=replacement_plan,
            version=1,
            modules=["sales", "inventory"],
            limits={"users": 20},
            published_at=timezone.now(),
        )
        period_end = timezone.now() + timedelta(days=365)
        self.client.force_authenticate(admin)
        response = self.client.post(
            reverse("platform-subscription-configure", args=[self.subscription.pk]),
            {
                "plan_version": replacement.pk,
                "status": "active",
                "period_ends_at": period_end.isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.plan_version, replacement)
        self.assertEqual(self.subscription.revision, 2)
        event = self.subscription.events.get(event_type="configured")
        self.assertEqual(event.metadata["from_plan_version"], self.version.pk)
        self.assertEqual(event.metadata["to_plan_version"], replacement.pk)

    def test_platform_cannot_assign_an_unpublished_plan_version(self):
        admin = User.objects.create_superuser(
            email="draft-plan@test.local", password="long-password"
        )
        draft = PlanVersion.objects.create(
            plan=self.plan,
            version=2,
            modules=["sales"],
        )
        self.client.force_authenticate(admin)
        response = self.client.post(
            reverse("platform-subscription-configure", args=[self.subscription.pk]),
            {"plan_version": draft.pk},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_published_plan_version_is_immutable(self):
        self.version.price = 999
        with self.assertRaises(DjangoValidationError):
            self.version.save()
