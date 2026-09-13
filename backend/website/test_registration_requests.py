from datetime import timedelta
from uuid import uuid4

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import User
from org.models import Company
from subscriptions.models import Plan, PlanVersion, Subscription
from subscriptions.models import SubscriptionPayment
from website.models import OwnerInvitation, RegistrationRequest


class RegistrationRequestTests(APITestCase):
    def setUp(self):
        plan = Plan.objects.create(code="business", name="Business")
        self.version = PlanVersion.objects.create(
            plan=plan, version=1, currency="USD", price=20,
            modules=["users", "org", "inventory", "sales"], limits={"users": 10},
            published_at=timezone.now(),
        )
        self.body = {
            "request_uuid": str(uuid4()),
            "company_name": "Northwind Trading",
            "contact_name": "Amina Owner",
            "email": "amina@northwind.test",
            "phone": "+249111222333",
            "country": "SD",
            "timezone_name": "Africa/Khartoum",
            "estimated_users": 6,
            "estimated_branches": 2,
            "delivery_mode": "saas",
            "plan_version": self.version.pk,
            "privacy_version": "2026-09",
        }

    def test_public_request_is_idempotent_and_does_not_expose_tenants(self):
        url = reverse("registration-request")
        first = self.client.post(url, self.body, format="json")
        again = self.client.post(url, self.body, format="json")
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(again.status_code, 200, again.data)
        self.assertEqual(RegistrationRequest.objects.count(), 1)
        self.assertEqual(set(first.data), {"reference", "status"})

    def test_public_endpoint_only_lists_published_public_plans(self):
        hidden_plan = Plan.objects.create(code="hidden", name="Hidden", is_public=False)
        PlanVersion.objects.create(
            plan=hidden_plan, version=1, modules=["sales"], published_at=timezone.now()
        )
        response = self.client.get(reverse("public-plan-list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.data], [self.version.pk])

    def test_platform_provisions_once_then_owner_activates(self):
        registration = RegistrationRequest.objects.create(
            request_uuid=uuid4(), company_name="Provisioned Co", contact_name="Owner",
            email="owner@provisioned.test", phone="+2491", country="SD",
            plan_version=self.version, privacy_version="2026-09",
            status=RegistrationRequest.APPROVED,
        )
        platform_admin = User.objects.create_superuser("platform@example.test", "secure-password")
        self.client.force_authenticate(platform_admin)
        provision_url = reverse("platform-registration-request-provision", args=[registration.pk])
        response = self.client.post(provision_url, {}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        token = response.data["owner_invitation_token"]
        registration.refresh_from_db()
        self.assertEqual(registration.status, RegistrationRequest.PROVISIONED)
        self.assertIsNotNone(registration.company_id)
        self.assertTrue(
            Subscription.objects.filter(
                company=registration.company, status="trialing"
            ).exists()
        )
        self.assertTrue(registration.company.branches.filter(name="Main Branch").exists())
        self.assertEqual(registration.company.users.get().role.name, "Business Owner")

        second = self.client.post(provision_url, {}, format="json")
        self.assertEqual(second.status_code, 200, second.data)
        self.assertNotIn("owner_invitation_token", second.data)
        self.assertEqual(Company.objects.filter(name="Provisioned Co").count(), 1)

        accept = self.client.post(
            reverse("owner-invitation-accept"),
            {"token": token, "password": "a-sufficiently-secure-password"}, format="json",
        )
        self.assertEqual(accept.status_code, 200, accept.data)
        invitation = OwnerInvitation.objects.get(registration_request=registration)
        self.assertIsNotNone(invitation.accepted_at)
        self.assertTrue(
            registration.company.users.get().check_password(
                "a-sufficiently-secure-password"
            )
        )

    def test_tenant_cannot_read_platform_registration_inbox(self):
        RegistrationRequest.objects.create(
            request_uuid=uuid4(), company_name="Prospect", contact_name="Person",
            email="person@prospect.test", phone="+2491", country="SD",
            plan_version=self.version, privacy_version="2026-09",
        )
        tenant = Company.objects.create(name="Tenant")
        member = User.objects.create_user("member@tenant.test", "secure-password", company=tenant)
        self.client.force_authenticate(member)
        response = self.client.get(reverse("platform-registration-request-list"))
        self.assertEqual(response.status_code, 403)

    def test_platform_overview_has_commercial_counts_only(self):
        registration = RegistrationRequest.objects.create(
            request_uuid=uuid4(), company_name="Awaiting Co", contact_name="Person",
            email="awaiting@example.test", phone="+2491", country="SD",
            plan_version=self.version, privacy_version="2026-09",
        )
        company = Company.objects.create(name="Trial Co")
        Subscription.objects.create(
            company=company, plan_version=self.version, status=Subscription.TRIALING,
            starts_at=timezone.now(), trial_ends_at=timezone.now() + timedelta(days=3),
        )
        owner = User.objects.create_user("owner@trial.test", "secure-password", company=company)
        SubscriptionPayment.objects.create(
            company=company, amount=20, currency="USD", method="cash", recorded_by=owner
        )
        platform_admin = User.objects.create_superuser("overview@example.test", "secure-password")
        self.client.force_authenticate(platform_admin)
        response = self.client.get(reverse("platform-overview"))
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["counts"]["registration_attention"], 1)
        self.assertEqual(response.data["counts"]["trialing"], 1)
        self.assertEqual(response.data["counts"]["pending_payments"], 1)
        self.assertEqual(response.data["registration_attention"][0]["id"], registration.pk)
        self.assertNotIn("sales", response.data)
