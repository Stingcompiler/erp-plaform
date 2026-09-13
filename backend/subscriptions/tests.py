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
    SubscriptionInvoice,
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

    def test_platform_verifies_full_payment_and_closes_invoice(self):
        admin = User.objects.create_superuser(
            email="payments@test.local", password="long-password"
        )
        now = timezone.now()
        invoice = SubscriptionInvoice.objects.create(
            company=self.company,
            subscription=self.subscription,
            number="SUB-100",
            status=SubscriptionInvoice.ISSUED,
            period_start=now.date(),
            period_end=(now + timedelta(days=30)).date(),
            currency="USD",
            amount="50.00",
            due_at=now + timedelta(days=7),
            issued_at=now,
        )
        payment = SubscriptionPayment.objects.create(
            company=self.company,
            amount="50.00",
            currency="USD",
            method="cash",
            recorded_by=self.owner,
        )
        self.client.force_authenticate(admin)
        response = self.client.post(
            reverse("platform-subscription-payment-verify", args=[payment.pk]),
            {"allocations": [{"invoice_id": invoice.pk, "amount": "50.00"}]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        payment.refresh_from_db()
        invoice.refresh_from_db()
        self.subscription.refresh_from_db()
        self.assertEqual(payment.status, SubscriptionPayment.VERIFIED)
        self.assertEqual(invoice.status, SubscriptionInvoice.PAID)
        self.assertIsNotNone(invoice.entitlement_granted_at)
        self.assertEqual(self.subscription.status, Subscription.ACTIVE)
        self.assertEqual(
            SubscriptionEvent.objects.filter(
                subscription=self.subscription, event_type="invoice_period_granted"
            ).count(),
            1,
        )

    def test_verifying_payment_twice_does_not_grant_the_invoice_period_twice(self):
        admin = User.objects.create_superuser(
            email="replay-payment@test.local", password="long-password"
        )
        now = timezone.now()
        invoice = SubscriptionInvoice.objects.create(
            company=self.company,
            subscription=self.subscription,
            number="SUB-REPLAY",
            status=SubscriptionInvoice.ISSUED,
            period_start=now.date(),
            period_end=(now + timedelta(days=60)).date(),
            currency="USD",
            amount="50.00",
            due_at=now + timedelta(days=7),
        )
        payment = SubscriptionPayment.objects.create(
            company=self.company,
            amount="50.00",
            currency="USD",
            method="cash",
            recorded_by=self.owner,
        )
        self.client.force_authenticate(admin)
        url = reverse("platform-subscription-payment-verify", args=[payment.pk])
        body = {"allocations": [{"invoice_id": invoice.pk, "amount": "50.00"}]}
        self.assertEqual(
            self.client.post(url, body, format="json").status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            self.client.post(url, body, format="json").status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            SubscriptionEvent.objects.filter(
                subscription=self.subscription, event_type="invoice_period_granted"
            ).count(),
            1,
        )

    def test_paid_invoice_does_not_reverse_manual_suspension(self):
        self.subscription.status = Subscription.SUSPENDED
        self.subscription.suspended_reason = "Manual compliance review"
        self.subscription.save(update_fields=["status", "suspended_reason"])
        admin = User.objects.create_superuser(
            email="suspended-payment@test.local", password="long-password"
        )
        now = timezone.now()
        invoice = SubscriptionInvoice.objects.create(
            company=self.company,
            subscription=self.subscription,
            number="SUB-SUSPENDED",
            status=SubscriptionInvoice.ISSUED,
            period_start=now.date(),
            period_end=(now + timedelta(days=30)).date(),
            currency="USD",
            amount="50.00",
            due_at=now + timedelta(days=7),
        )
        payment = SubscriptionPayment.objects.create(
            company=self.company,
            amount="50.00",
            currency="USD",
            method="cash",
            recorded_by=self.owner,
        )
        self.client.force_authenticate(admin)
        response = self.client.post(
            reverse("platform-subscription-payment-verify", args=[payment.pk]),
            {"allocations": [{"invoice_id": invoice.pk, "amount": "50.00"}]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, Subscription.SUSPENDED)

    def test_platform_issues_numbered_invoice_for_matching_subscription(self):
        admin = User.objects.create_superuser(
            email="issue-invoice@test.local", password="long-password"
        )
        now = timezone.now()
        self.client.force_authenticate(admin)
        response = self.client.post(
            reverse("platform-subscription-invoice-list"),
            {
                "company": self.company.pk,
                "subscription": self.subscription.pk,
                "period_start": now.date().isoformat(),
                "period_end": (now + timedelta(days=30)).date().isoformat(),
                "currency": "USD",
                "amount": "50.00",
                "due_at": (now + timedelta(days=7)).isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["status"], SubscriptionInvoice.ISSUED)
        self.assertRegex(response.data["number"], r"^VSUB-\d{6}$")

    def test_platform_rejects_partially_allocated_payment(self):
        admin = User.objects.create_superuser(
            email="partial-payment@test.local", password="long-password"
        )
        now = timezone.now()
        invoice = SubscriptionInvoice.objects.create(
            company=self.company,
            subscription=self.subscription,
            number="SUB-101",
            status=SubscriptionInvoice.ISSUED,
            period_start=now.date(),
            period_end=(now + timedelta(days=30)).date(),
            currency="USD",
            amount="50.00",
            due_at=now + timedelta(days=7),
        )
        payment = SubscriptionPayment.objects.create(
            company=self.company,
            amount="50.00",
            currency="USD",
            method="cash",
            recorded_by=self.owner,
        )
        self.client.force_authenticate(admin)
        response = self.client.post(
            reverse("platform-subscription-payment-verify", args=[payment.pk]),
            {"allocations": [{"invoice_id": invoice.pk, "amount": "40.00"}]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        payment.refresh_from_db()
        self.assertEqual(payment.status, SubscriptionPayment.PENDING)

    def test_published_plan_version_is_immutable(self):
        self.version.price = 999
        with self.assertRaises(DjangoValidationError):
            self.version.save()


class PaymentRejectionAndCancellationTests(APITestCase):
    def setUp(self):
        self.owner_role = Role.objects.create(
            name="Business Owner", scope_level=Role.SCOPE_BUSINESS
        )
        self.company = Company.objects.create(name="Cancelling Co")
        self.owner = User.objects.create_user(
            email="owner@cancel.test", password="long-password",
            company=self.company, role=self.owner_role,
        )
        self.admin = User.objects.create_superuser(
            email="platform@cancel.test", password="long-password"
        )
        plan = Plan.objects.create(code="business", name="Business")
        self.version = PlanVersion.objects.create(
            plan=plan, version=1, modules=["*"], limits={}, published_at=timezone.now()
        )
        self.subscription = Subscription.objects.create(
            company=self.company, plan_version=self.version, status=Subscription.ACTIVE,
            starts_at=timezone.now(), period_ends_at=timezone.now() + timedelta(days=30),
            grace_ends_at=timezone.now() + timedelta(days=40),
        )

    def _pending_payment(self):
        return SubscriptionPayment.objects.create(
            company=self.company, amount="50.00", currency="USD", method="cash",
            recorded_by=self.owner,
        )

    def test_platform_rejects_pending_payment_with_reason(self):
        payment = self._pending_payment()
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            reverse("platform-subscription-payment-reject", args=[payment.pk]),
            {"reason": "Reference does not match any transfer."}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        payment.refresh_from_db()
        self.assertEqual(payment.status, SubscriptionPayment.REJECTED)
        self.assertEqual(payment.rejection_reason, "Reference does not match any transfer.")
        self.assertEqual(payment.verified_by, self.admin)
        # The company sees the reason on its own payment list.
        self.client.force_authenticate(self.owner)
        listed = self.client.get(reverse("subscription-payment-list"))
        self.assertEqual(listed.status_code, 200)
        rows = listed.data["results"] if "results" in listed.data else listed.data
        self.assertEqual(rows[0]["status"], "rejected")
        self.assertEqual(rows[0]["rejection_reason"], "Reference does not match any transfer.")

    def test_rejection_requires_reason_and_pending_status(self):
        payment = self._pending_payment()
        self.client.force_authenticate(self.admin)
        no_reason = self.client.post(
            reverse("platform-subscription-payment-reject", args=[payment.pk]),
            {"reason": "  "}, format="json",
        )
        self.assertEqual(no_reason.status_code, status.HTTP_400_BAD_REQUEST)
        payment.status = SubscriptionPayment.VERIFIED
        payment.save(update_fields=["status"])
        verified = self.client.post(
            reverse("platform-subscription-payment-reject", args=[payment.pk]),
            {"reason": "too late"}, format="json",
        )
        self.assertEqual(verified.status_code, status.HTTP_400_BAD_REQUEST)
        payment.refresh_from_db()
        self.assertEqual(payment.status, SubscriptionPayment.VERIFIED)

    def test_cancel_at_period_end_skips_grace_and_ends_access(self):
        from core.entitlements import _saas_decision

        self.subscription.cancel_at_period_end = True
        self.subscription.save(update_fields=["cancel_at_period_end"])
        before = _saas_decision(self.company, timezone.now())
        self.assertEqual(before.state, Subscription.ACTIVE)
        self.assertTrue(before.allow_writes)
        self.assertEqual(before.valid_until, self.subscription.period_ends_at)

        after = _saas_decision(self.company, self.subscription.period_ends_at + timedelta(hours=1))
        self.assertEqual(after.state, Subscription.CANCELLED)
        self.assertFalse(after.allow_writes)

        # Without the flag the same moment falls into grace and still allows writes.
        self.subscription.cancel_at_period_end = False
        self.subscription.save(update_fields=["cancel_at_period_end"])
        graced = _saas_decision(self.company, self.subscription.period_ends_at + timedelta(hours=1))
        self.assertEqual(graced.state, Subscription.GRACE)
        self.assertTrue(graced.allow_writes)
