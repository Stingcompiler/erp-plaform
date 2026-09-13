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


class RegistrationLifecycleTests(APITestCase):
    """Reissuing invitations, swapping a stale plan, and trial boundaries."""

    def setUp(self):
        self.plan = Plan.objects.create(code="business", name="Business")
        self.version = PlanVersion.objects.create(
            plan=self.plan, version=1, currency="USD", price=20,
            modules=["users", "org", "sales"], limits={"users": 10},
            published_at=timezone.now(),
        )
        self.admin = User.objects.create_superuser("platform@example.test", "secure-password")
        self.client.force_authenticate(self.admin)

    def _request(self, **overrides):
        data = dict(
            request_uuid=uuid4(), company_name="Lifecycle Co", contact_name="Owner",
            email="owner@lifecycle.test", phone="+2491", country="SD",
            plan_version=self.version, privacy_version="2026-09",
            status=RegistrationRequest.APPROVED,
        )
        data.update(overrides)
        return RegistrationRequest.objects.create(**data)

    def _provision(self, registration):
        response = self.client.post(
            reverse("platform-registration-request-provision", args=[registration.pk]),
            {}, format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        registration.refresh_from_db()
        return response.data["owner_invitation_token"]

    def test_expired_invitation_can_be_reissued_and_old_link_dies(self):
        registration = self._request()
        first_token = self._provision(registration)
        OwnerInvitation.objects.filter(registration_request=registration).update(
            expires_at=timezone.now() - timedelta(hours=1)
        )
        accept_url = reverse("owner-invitation-accept")
        expired = self.client.post(
            accept_url, {"token": first_token, "password": "a-sufficiently-secure-password"},
            format="json",
        )
        self.assertEqual(expired.status_code, 400)

        reissue_url = reverse(
            "platform-registration-request-reissue-invitation", args=[registration.pk]
        )
        response = self.client.post(reissue_url, {}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        new_token = response.data["owner_invitation_token"]
        self.assertNotEqual(new_token, first_token)
        self.assertEqual(
            OwnerInvitation.objects.filter(
                registration_request=registration, revoked_at__isnull=False
            ).count(),
            1,
        )
        accepted = self.client.post(
            accept_url, {"token": new_token, "password": "a-sufficiently-secure-password"},
            format="json",
        )
        self.assertEqual(accepted.status_code, 200, accepted.data)
        owner = registration.company.users.get()
        self.assertTrue(owner.check_password("a-sufficiently-secure-password"))

    def test_reissue_requires_a_provisioned_request(self):
        registration = self._request()
        response = self.client.post(
            reverse("platform-registration-request-reissue-invitation", args=[registration.pk]),
            {}, format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(OwnerInvitation.objects.filter(registration_request=registration).exists())

    def test_invitation_rejected_for_deactivated_owner(self):
        registration = self._request()
        token = self._provision(registration)
        registration.company.users.update(is_active=False)
        response = self.client.post(
            reverse("owner-invitation-accept"),
            {"token": token, "password": "a-sufficiently-secure-password"}, format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(
            registration.company.users.get().check_password("a-sufficiently-secure-password")
        )

    def test_stale_plan_blocks_approval_until_platform_swaps_it(self):
        registration = self._request(status=RegistrationRequest.SUBMITTED)
        self.plan.is_public = False
        self.plan.save(update_fields=["is_public"])
        approve_url = reverse("platform-registration-request-approve", args=[registration.pk])
        blocked = self.client.post(approve_url, {}, format="json")
        self.assertEqual(blocked.status_code, 400, blocked.data)

        live_plan = Plan.objects.create(code="starter", name="Starter")
        live_version = PlanVersion.objects.create(
            plan=live_plan, version=1, currency="USD", price=5,
            modules=["users", "org"], limits={}, published_at=timezone.now(),
        )
        detail_url = reverse("platform-registration-request-detail", args=[registration.pk])
        swapped = self.client.patch(detail_url, {"plan_version": live_version.pk}, format="json")
        self.assertEqual(swapped.status_code, 200, swapped.data)
        self.assertEqual(swapped.data["plan_name"], "Starter")
        # Swapping *to* an unavailable plan is refused.
        refused = self.client.patch(detail_url, {"plan_version": self.version.pk}, format="json")
        self.assertEqual(refused.status_code, 400)

        approved = self.client.post(approve_url, {}, format="json")
        self.assertEqual(approved.status_code, 200, approved.data)
        self.assertEqual(approved.data["status"], RegistrationRequest.APPROVED)

    def test_plan_of_provisioned_request_is_frozen(self):
        registration = self._request()
        self._provision(registration)
        other = PlanVersion.objects.create(
            plan=self.plan, version=2, currency="USD", price=30,
            modules=["users"], limits={}, published_at=timezone.now(),
        )
        response = self.client.patch(
            reverse("platform-registration-request-detail", args=[registration.pk]),
            {"plan_version": other.pk}, format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_entitlement_valid_until_is_the_trial_end(self):
        from core.entitlements import _saas_decision

        registration = self._request()
        self._provision(registration)
        subscription = registration.company.subscription
        now = timezone.now()
        decision = _saas_decision(registration.company, now)
        self.assertEqual(decision.state, Subscription.TRIALING)
        self.assertTrue(decision.allow_writes)
        self.assertEqual(decision.valid_until, subscription.trial_ends_at)
        # Past the trial with no grace: read-only.
        after = _saas_decision(registration.company, subscription.trial_ends_at + timedelta(days=1))
        self.assertEqual(after.state, Subscription.READ_ONLY)
        self.assertFalse(after.allow_writes)
