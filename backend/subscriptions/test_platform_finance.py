"""The finance report counts only verified money, never mixes currencies,
normalises yearly plans to MRR and reads trial conversion from events."""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Role, User
from org.models import Company
from subscriptions.models import (
    PaymentAllocation,
    Plan,
    PlanVersion,
    Subscription,
    SubscriptionEvent,
    SubscriptionInvoice,
    SubscriptionPayment,
)


class PlatformFinanceTests(TestCase):
    def setUp(self):
        now = timezone.now()
        self.admin = User.objects.create_superuser(
            email="root@vezano.test", password="Root-passw0rd!"
        )
        owner_role = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        monthly = Plan.objects.create(code="shop", name="Shop")
        yearly = Plan.objects.create(code="pro", name="Pro")
        self.v_month = PlanVersion.objects.create(
            plan=monthly, version=1, modules=["*"], currency="SDG", price=Decimal("120000"),
            billing_cycle="monthly", published_at=now,
        )
        self.v_year = PlanVersion.objects.create(
            plan=yearly, version=1, modules=["*"], currency="USD", price=Decimal("1200"),
            billing_cycle="yearly", published_at=now,
        )
        self.a = Company.objects.create(name="A")
        self.b = Company.objects.create(name="B")
        self.c = Company.objects.create(name="C")
        self.owner_a = User.objects.create_user(
            email="a@x.test", password="Owner-passw0rd!x", company=self.a, role=owner_role
        )
        self.sub_a = Subscription.objects.create(
            company=self.a, plan_version=self.v_month, status="active", starts_at=now,
            period_ends_at=now + timedelta(days=20),
        )
        self.sub_b = Subscription.objects.create(
            company=self.b, plan_version=self.v_year, status="active", starts_at=now,
            period_ends_at=now + timedelta(days=300),
        )
        self.sub_c = Subscription.objects.create(
            company=self.c, plan_version=self.v_month, status="trialing", starts_at=now,
            trial_ends_at=now + timedelta(days=10),
        )
        SubscriptionEvent.objects.create(
            subscription=self.sub_a, event_type="status_changed",
            from_status="trialing", to_status="active",
        )
        # A: one issued invoice, half paid by a verified payment; a pending
        # payment that must not count.
        self.inv_a = SubscriptionInvoice.objects.create(
            company=self.a, subscription=self.sub_a, number="VSUB-1", status="issued",
            period_start=now.date(), period_end=(now + timedelta(days=30)).date(),
            currency="SDG", amount=Decimal("120000"), due_at=now - timedelta(days=1),
            issued_at=now,
        )
        paid = SubscriptionPayment.objects.create(
            company=self.a, amount=Decimal("50000"), currency="SDG", method="cash",
            status="verified", recorded_by=self.owner_a, verified_by=self.admin, verified_at=now,
        )
        PaymentAllocation.objects.create(payment=paid, invoice=self.inv_a, amount=Decimal("50000"))
        SubscriptionPayment.objects.create(
            company=self.a, amount=Decimal("70000"), currency="SDG", method="cash",
            status="pending", recorded_by=self.owner_a,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_report_numbers(self):
        response = self.client.get("/api/platform/finance/?months=6")
        self.assertEqual(response.status_code, 200, response.data)
        data = response.data
        by_currency = {c["currency"]: c for c in data["currencies"]}
        sdg, usd = by_currency["SDG"], by_currency["USD"]
        self.assertEqual(sdg["mrr"], "120000.00")           # A only; C is a trial
        self.assertEqual(usd["mrr"], "100.00")              # 1200 / 12
        self.assertEqual(usd["arr"], "1200.00")
        self.assertEqual(sdg["collected_month"], "50000.00")  # pending 70000 ignored
        self.assertEqual(sdg["outstanding"], "70000.00")
        self.assertEqual(sdg["overdue"], "70000.00")
        shop = next(p for p in sdg["by_plan"] if p["code"] == "shop")
        self.assertEqual((shop["active"], shop["trialing"]), (1, 1))
        self.assertEqual(shop["collected_window"], "50000.00")
        self.assertEqual(shop["outstanding"], "70000.00")
        self.assertEqual(len(sdg["monthly"]), 6)
        self.assertEqual(sdg["monthly"][-1]["invoiced"], "120000.00")
        self.assertEqual(sdg["monthly"][-1]["collected"], "50000.00")
        self.assertEqual(data["statuses"], {"active": 2, "trialing": 1})
        self.assertEqual(
            data["trial_conversion"], {"ever_trialing": 2, "converted": 1, "rate": 0.5}
        )
        self.assertEqual(data["monthly_subscriptions"][-1]["new"], 3)
        first = data["companies"][0]
        self.assertEqual((first["company"], first["outstanding"]), ("A", "70000.00"))

    def test_csv_export(self):
        response = self.client.get("/api/platform/finance/?format=csv")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        body = response.content.decode("utf-8-sig")
        self.assertIn("company,plan,currency,status", body.splitlines()[0])
        self.assertIn("A,Shop,SDG,active,120000.00,70000.00", body)

    def test_needs_billing_capability(self):
        role = Role.objects.create(name="Support Agent", scope_level=Role.SCOPE_PLATFORM)
        agent = User.objects.create_user(
            email="agent@vezano.test", password="Agent-passw0rd!x", role=role
        )
        self.assertTrue(agent.is_platform_admin)
        client = APIClient()
        client.force_authenticate(agent)
        self.assertEqual(client.get("/api/platform/finance/").status_code, 403)
        tenant = APIClient()
        tenant.force_authenticate(self.owner_a)
        self.assertEqual(tenant.get("/api/platform/finance/").status_code, 403)
