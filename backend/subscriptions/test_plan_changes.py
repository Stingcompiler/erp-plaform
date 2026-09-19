"""Plan changes: an upgrade is invoiced pro rata and switches when paid; a
downgrade waits for the period end and is refused while usage exceeds the
target; one open request per company; the platform decides."""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Role, User
from org.models import Branch, Company, Device
from subscriptions.models import (
    PlanChangeRequest,
    Plan,
    PlanVersion,
    Subscription,
    SubscriptionEvent,
    SubscriptionInvoice,
    SubscriptionPayment,
)
from subscriptions.plan_changes import apply_due_downgrades
from subscriptions.services import verify_and_allocate_payment


@override_settings(SUBSCRIPTION_POLICY="enforce")
class PlanChangeTests(TestCase):
    def setUp(self):
        now = timezone.now()
        self.now = now
        self.admin = User.objects.create_superuser(
            email="root@vezano.test", password="Root-passw0rd!"
        )
        owner_role = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        self.company = Company.objects.create(name="Alpha", business_type="enterprise")
        Branch.objects.create(company=self.company, name="Main")
        self.owner = User.objects.create_user(
            email="owner@alpha.test", password="Owner-passw0rd!x", company=self.company,
            role=owner_role, full_name="Alpha Owner",
        )
        basic = Plan.objects.create(code="basic", name="Basic", sort_order=1)
        pro = Plan.objects.create(code="pro", name="Pro", sort_order=2)
        self.basic = PlanVersion.objects.create(
            plan=basic, version=1, modules=["*"], currency="SDG", price=Decimal("100000"),
            limits={"devices": 2}, published_at=now,
        )
        self.pro = PlanVersion.objects.create(
            plan=pro, version=1, modules=["*"], currency="SDG", price=Decimal("200000"),
            limits={"devices": 5}, published_at=now,
        )
        # Exactly half of a 30-day period remains.
        self.subscription = Subscription.objects.create(
            company=self.company, plan_version=self.basic, status=Subscription.ACTIVE,
            starts_at=now - timedelta(days=15), period_ends_at=now + timedelta(days=15),
        )
        self.owner_client = APIClient()
        self.owner_client.force_authenticate(self.owner)
        self.admin_client = APIClient()
        self.admin_client.force_authenticate(self.admin)

    def test_owner_sees_options_with_prorated_cost(self):
        response = self.owner_client.get("/api/subscription/plan-changes/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNone(response.data["current"])
        option = next(o for o in response.data["options"] if o["code"] == "pro")
        self.assertEqual(option["kind"], "upgrade")
        # (200000 - 100000) × 0.5
        self.assertEqual(Decimal(option["due_now"]), Decimal("50000.00"))

    def test_upgrade_is_invoiced_and_switches_when_paid(self):
        asked = self.owner_client.post(
            "/api/subscription/plan-changes/", {"to_version": self.pro.pk, "note": "more tills"},
            format="json",
        )
        self.assertEqual(asked.status_code, 201, asked.data)
        self.assertEqual(asked.data["kind"], "upgrade")
        # Second open request is refused.
        again = self.owner_client.post(
            "/api/subscription/plan-changes/", {"to_version": self.pro.pk}, format="json"
        )
        self.assertEqual(again.status_code, 400)

        pending = self.admin_client.get("/api/platform/plan-changes/?status=pending")
        rows = pending.data["results"] if "results" in pending.data else pending.data
        self.assertEqual(len(rows), 1)

        approved = self.admin_client.post(
            f"/api/platform/plan-changes/{asked.data['id']}/approve/", {"note": "ok"},
            format="json",
        )
        self.assertEqual(approved.status_code, 200, approved.data)
        self.assertEqual(approved.data["status"], "approved")
        self.assertEqual(Decimal(approved.data["invoice_amount"]), Decimal("50000.00"))
        invoice = SubscriptionInvoice.objects.get(number=approved.data["invoice_number"])
        self.assertEqual(invoice.status, SubscriptionInvoice.ISSUED)
        self.assertEqual(invoice.line_snapshot[0]["kind"], "upgrade")
        # Not switched yet.
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.plan_version_id, self.basic.pk)

        payment = SubscriptionPayment.objects.create(
            company=self.company, amount=Decimal("50000"), currency="SDG", method="cash",
            recorded_by=self.owner,
        )
        verify_and_allocate_payment(
            payment.pk, self.admin, [{"invoice_id": invoice.pk, "amount": Decimal("50000")}]
        )
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.plan_version_id, self.pro.pk)
        # Paying the difference must not extend the period.
        self.assertEqual(self.subscription.period_ends_at, self.now + timedelta(days=15))
        change = PlanChangeRequest.objects.get(pk=asked.data["id"])
        self.assertEqual(change.status, PlanChangeRequest.APPLIED)
        self.assertTrue(
            SubscriptionEvent.objects.filter(
                subscription=self.subscription, event_type="plan_changed"
            ).exists()
        )

    def test_downgrade_waits_for_period_end_and_is_refused_over_usage(self):
        self.subscription.plan_version = self.pro
        self.subscription.save()
        for i in range(3):
            Device.objects.create(company=self.company, device_id=f"D{i}")
        refused = self.owner_client.post(
            "/api/subscription/plan-changes/", {"to_version": self.basic.pk}, format="json"
        )
        self.assertEqual(refused.status_code, 400)
        self.assertEqual(refused.data["code"], "usage_exceeds_target")
        self.assertEqual(refused.data["over"]["devices"], {"used": 3, "limit": 2})
        options = self.owner_client.get("/api/subscription/plan-changes/").data["options"]
        basic = next(o for o in options if o["code"] == "basic")
        self.assertEqual(basic["kind"], "downgrade")
        self.assertIn("devices", basic["blocked_by"])

        Device.objects.filter(device_id="D2").update(is_active=False)
        asked = self.owner_client.post(
            "/api/subscription/plan-changes/", {"to_version": self.basic.pk}, format="json"
        )
        self.assertEqual(asked.status_code, 201, asked.data)
        approved = self.admin_client.post(
            f"/api/platform/plan-changes/{asked.data['id']}/approve/", format="json"
        )
        self.assertEqual(approved.data["status"], "approved")
        self.assertIsNone(approved.data["invoice_number"])
        self.assertIsNotNone(approved.data["apply_at"])
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.plan_version_id, self.pro.pk)
        # Daily scan: nothing before the period ends, the switch after.
        self.assertEqual(apply_due_downgrades(self.now), 0)
        self.assertEqual(apply_due_downgrades(self.now + timedelta(days=16)), 1)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.plan_version_id, self.basic.pk)

    def test_reject_and_cancel(self):
        asked = self.owner_client.post(
            "/api/subscription/plan-changes/", {"to_version": self.pro.pk}, format="json"
        ).data
        rejected = self.admin_client.post(
            f"/api/platform/plan-changes/{asked['id']}/reject/", {"note": "call us"},
            format="json",
        )
        self.assertEqual(rejected.data["status"], "rejected")
        self.assertEqual(rejected.data["decision_note"], "call us")

        asked = self.owner_client.post(
            "/api/subscription/plan-changes/", {"to_version": self.pro.pk}, format="json"
        ).data
        self.admin_client.post(f"/api/platform/plan-changes/{asked['id']}/approve/")
        cancelled = self.owner_client.post(f"/api/subscription/plan-changes/{asked['id']}/cancel/")
        self.assertEqual(cancelled.data["status"], "cancelled")
        # Its unpaid invoice is voided, not left to be collected.
        change = PlanChangeRequest.objects.get(pk=asked["id"])
        self.assertEqual(change.invoice.status, SubscriptionInvoice.VOID)

    def test_platform_badge_counts_pending_requests(self):
        from website.attention import subscription_payments_to_verify

        since = self.now - timedelta(days=1)
        self.assertEqual(subscription_payments_to_verify(self.admin, since), 0)
        self.owner_client.post(
            "/api/subscription/plan-changes/", {"to_version": self.pro.pk}, format="json"
        )
        self.assertEqual(subscription_payments_to_verify(self.admin, since), 1)

    def test_non_owner_and_tenant_are_kept_out(self):
        sales_role = Role.objects.create(name="Sales Officer", scope_level=Role.SCOPE_BRANCH)
        clerk = User.objects.create_user(
            email="clerk@alpha.test", password="Clerk-passw0rd!x", company=self.company,
            role=sales_role, branch=self.company.branches.first(),
        )
        client = APIClient()
        client.force_authenticate(clerk)
        self.assertEqual(client.get("/api/subscription/plan-changes/").status_code, 403)
        self.assertEqual(self.owner_client.get("/api/platform/plan-changes/").status_code, 403)


@override_settings(SUBSCRIPTION_POLICY="enforce")
class AddonTests(TestCase):
    def setUp(self):
        now = timezone.now()
        self.now = now
        self.admin = User.objects.create_superuser(
            email="root@vezano.test", password="Root-passw0rd!"
        )
        owner_role = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        self.company = Company.objects.create(name="Alpha", business_type="enterprise")
        self.owner = User.objects.create_user(
            email="owner@alpha.test", password="Owner-passw0rd!x", company=self.company,
            role=owner_role,
        )
        plan = Plan.objects.create(code="shop", name="Shop")
        self.version = PlanVersion.objects.create(
            plan=plan, version=1, modules=["*"], currency="SDG", price=Decimal("100000"),
            limits={"devices": 2}, addon_prices={"devices": "20000"}, published_at=now,
        )
        self.subscription = Subscription.objects.create(
            company=self.company, plan_version=self.version, status=Subscription.ACTIVE,
            starts_at=now - timedelta(days=15), period_ends_at=now + timedelta(days=15),
        )
        self.owner_client = APIClient()
        self.owner_client.force_authenticate(self.owner)
        self.admin_client = APIClient()
        self.admin_client.force_authenticate(self.admin)

    def _login_device(self, device_id):
        client = APIClient()
        return client.post(
            "/api/auth/login/",
            {"email": "owner@alpha.test", "password": "Owner-passw0rd!x", "device_id": device_id},
            format="json",
        )

    def test_buying_units_is_prorated_and_raises_the_limit_when_paid(self):
        offer = self.owner_client.get("/api/subscription/plan-changes/").data["addons"]
        self.assertEqual(offer[0]["resource"], "devices")
        self.assertEqual(Decimal(offer[0]["unit_due_now"]), Decimal("10000.00"))  # 20000 × 0.5

        asked = self.owner_client.post(
            "/api/subscription/plan-changes/", {"extra_delta": {"devices": 2}}, format="json"
        )
        self.assertEqual(asked.status_code, 201, asked.data)
        self.assertEqual(asked.data["kind"], "addon")
        approved = self.admin_client.post(
            f"/api/platform/plan-changes/{asked.data['id']}/approve/", format="json"
        )
        self.assertEqual(Decimal(approved.data["invoice_amount"]), Decimal("20000.00"))
        # Still two devices until paid.
        for d in ("A", "B"):
            self.assertEqual(self._login_device(d).status_code, 200)
        self.assertEqual(self._login_device("C").status_code, 403)

        invoice = SubscriptionInvoice.objects.get(number=approved.data["invoice_number"])
        payment = SubscriptionPayment.objects.create(
            company=self.company, amount=Decimal("20000"), currency="SDG", method="cash",
            recorded_by=self.owner,
        )
        verify_and_allocate_payment(
            payment.pk, self.admin, [{"invoice_id": invoice.pk, "amount": Decimal("20000")}]
        )
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.extra_limits, {"devices": 2})
        self.assertEqual(self._login_device("C").status_code, 200)
        self.assertEqual(self._login_device("D").status_code, 200)
        self.assertEqual(self._login_device("E").status_code, 403)
        # The renewal now carries the add-on.
        page = self.owner_client.get("/api/subscription/").data
        self.assertEqual(page["subscription"]["recurring_amount"], "140000.00")
        self.assertEqual(page["subscription"]["addon_lines"][0]["units"], 2)
        self.assertEqual(page["usage"]["devices"]["limit"], 4)

    def test_removing_units_waits_and_is_refused_while_in_use(self):
        self.subscription.extra_limits = {"devices": 2}
        self.subscription.save()
        for i in range(4):
            Device.objects.create(company=self.company, device_id=f"D{i}")
        refused = self.owner_client.post(
            "/api/subscription/plan-changes/", {"extra_delta": {"devices": -1}}, format="json"
        )
        self.assertEqual(refused.status_code, 400)
        self.assertEqual(refused.data["code"], "usage_exceeds_target")
        Device.objects.filter(device_id="D3").update(is_active=False)
        asked = self.owner_client.post(
            "/api/subscription/plan-changes/", {"extra_delta": {"devices": -1}}, format="json"
        )
        self.assertEqual(asked.status_code, 201, asked.data)
        self.assertEqual(asked.data["kind"], "addon_remove")
        approved = self.admin_client.post(
            f"/api/platform/plan-changes/{asked.data['id']}/approve/", format="json"
        )
        self.assertIsNone(approved.data["invoice_number"])
        self.assertEqual(apply_due_downgrades(self.now + timedelta(days=16)), 1)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.extra_limits, {"devices": 1})

    def test_unpriced_resource_is_refused(self):
        response = self.owner_client.post(
            "/api/subscription/plan-changes/", {"extra_delta": {"users": 1}}, format="json"
        )
        self.assertEqual(response.status_code, 400)


@override_settings(SUBSCRIPTION_POLICY="enforce")
class PaymentCurrencyTests(TestCase):
    def test_owner_cannot_pay_in_another_currency(self):
        now = timezone.now()
        owner_role = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        company = Company.objects.create(name="Alpha")
        owner = User.objects.create_user(
            email="owner@alpha.test", password="Owner-passw0rd!x", company=company, role=owner_role
        )
        plan = Plan.objects.create(code="shop", name="Shop")
        version = PlanVersion.objects.create(
            plan=plan, version=1, modules=["*"], currency="SDG", price=Decimal("100000"),
            published_at=now,
        )
        Subscription.objects.create(
            company=company, plan_version=version, status=Subscription.ACTIVE,
            starts_at=now, period_ends_at=now + timedelta(days=30),
        )
        client = APIClient()
        client.force_authenticate(owner)
        wrong = client.post(
            "/api/subscription/payments/",
            {"amount": "100", "currency": "USD", "method": "cash"},
        )
        self.assertEqual(wrong.status_code, 400, wrong.data)
        self.assertIn("SDG", str(wrong.data["currency"]))
        right = client.post(
            "/api/subscription/payments/",
            {"amount": "100000", "currency": "SDG", "method": "cash"},
        )
        self.assertEqual(right.status_code, 201, right.data)
