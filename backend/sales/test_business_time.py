from datetime import timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import Role, User
from inventory.models import Product, StockMovement, Warehouse
from org.models import Branch, Company
from sales.models import Invoice, Payment


class BusinessTimeTests(APITestCase):
    """An offline sale that syncs later must be dated when it happened, not
    when the server finally saw it — reports, tax periods, and costing all
    read that business time. The server clock is kept separately for audit."""

    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        branch = Branch.objects.create(company=self.company, name="Main")
        owner = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        self.user = User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123", company=self.company, role=owner
        )
        self.warehouse = Warehouse.objects.create(company=self.company, branch=branch, name="WH")
        self.product = Product.objects.create(
            company=self.company, sku="T1", name="Widget",
            sale_price=Decimal("50.00"), cost_price=Decimal("20.00"),
        )
        self.client.force_authenticate(self.user)

    def _checkout(self, occurred_at=None, **extra):
        body = {
            "warehouse": self.warehouse.id,
            "lines": [{"product": self.product.id, "quantity": "1"}],
            "payment": {"method": "cash", "amount": "50.00"},
            **extra,
        }
        if occurred_at is not None:
            body["occurred_at"] = occurred_at.isoformat()
        return self.client.post(reverse("pos-checkout"), body, format="json")

    def test_offline_sale_keeps_its_own_time_on_every_record(self):
        sold_at = timezone.now() - timedelta(days=3, hours=4)
        response = self._checkout(sold_at)
        self.assertEqual(response.status_code, 201, response.data)
        invoice = Invoice.objects.get(pk=response.data["id"])
        movement = StockMovement.objects.get(reference_id=str(invoice.id))
        payment = Payment.objects.get(invoice=invoice)
        for stamp in (invoice.issued_at, movement.created_at, payment.recorded_at):
            self.assertLess(abs((stamp - sold_at).total_seconds()), 1)
        # Audit time is the server clock, i.e. now, not three days ago.
        for received in (invoice.received_at, movement.received_at, payment.received_at):
            self.assertLess(abs((received - timezone.now()).total_seconds()), 60)
        # Due date derives from the business date.
        self.assertEqual(invoice.due_date, sold_at.date())

    def test_online_sale_defaults_to_now(self):
        response = self._checkout()
        self.assertEqual(response.status_code, 201, response.data)
        invoice = Invoice.objects.get(pk=response.data["id"])
        self.assertLess(abs((invoice.issued_at - timezone.now()).total_seconds()), 60)

    def test_window_rejects_future_and_stale_timestamps(self):
        future = self._checkout(timezone.now() + timedelta(hours=1))
        self.assertEqual(future.status_code, 400)
        self.assertIn("occurred_at", future.data)
        stale = self._checkout(timezone.now() - timedelta(days=40))
        self.assertEqual(stale.status_code, 400)
        self.assertIn("occurred_at", stale.data)

    def test_reports_read_business_time(self):
        # 30 days back, inside the 31-day backdate window on every calendar
        # day; the previous "15th minus 31 days" fell outside it from the
        # 15th of each month onward and failed the suite for half the month.
        last_month = timezone.now() - timedelta(days=30)
        self._checkout(last_month)
        self._checkout()  # today
        response = self.client.get(
            reverse("report-sales-summary"),
            {"start": last_month.date().isoformat(), "end": last_month.date().isoformat()},
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["totals"]["invoice_count"], 1)

    def test_direct_payment_accepts_business_time(self):
        invoice_id = self._checkout(**{"payment": None}).data["id"]
        paid_at = timezone.now() - timedelta(days=2)
        response = self.client.post(
            reverse("payment-list"),
            {"invoice": invoice_id, "method": "cash", "amount": "50.00",
             "recorded_at": paid_at.isoformat()},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        payment = Payment.objects.get(invoice_id=invoice_id)
        self.assertLess(abs((payment.recorded_at - paid_at).total_seconds()), 1)
