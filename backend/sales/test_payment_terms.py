"""Credit sales get real payment terms.

The POS never set payment_terms_days, so every account sale was due on the
day it was sold and overdue from the next morning. Terms now come from the
sale payload, else the customer, else the company default — and existing
invoices are backfilled once.
"""

from datetime import timedelta
from decimal import Decimal
from importlib import import_module

from django.apps import apps
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Role, User
from inventory.models import Product, Warehouse
from org.models import Branch, Company
from sales.models import Customer, Invoice


def _local_day(invoice):
    """The day the invoice was issued in the company's calendar — what the
    due date counts from (UTC's date is a day behind after midnight)."""
    from django.utils import timezone as _tz

    from core.timezone import company_zone

    return _tz.localtime(invoice.issued_at, company_zone(invoice.company)).date()


class TermsBase(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha", default_payment_terms_days=30)
        self.branch = Branch.objects.create(company=self.company, name="Main")
        role = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        self.user = User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123", company=self.company, role=role,
        )
        self.wh = Warehouse.objects.create(company=self.company, branch=self.branch, name="W")
        self.product = Product.objects.create(
            company=self.company, sku="P1", name="Thing", sale_price=Decimal("10"),
        )
        self.customer = Customer.objects.create(company=self.company, name="Buyer")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _sell(self, **extra):
        body = {
            "warehouse": self.wh.pk, "customer": self.customer.pk,
            "lines": [{"product": self.product.pk, "quantity": "1", "unit_price": "10"}],
            "client_uuid": "11111111-1111-4111-8111-11111111111%d" % Invoice.objects.count(),
        }
        body.update(extra)
        response = self.client.post("/api/pos/checkout/", body, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return Invoice.objects.get(pk=response.data["id"])


class CheckoutTermsTests(TermsBase):
    def test_company_default_applies(self):
        inv = self._sell()
        self.assertEqual(inv.payment_terms_days, 30)
        self.assertEqual(inv.due_date, _local_day(inv) + timedelta(days=30))
        self.assertFalse(inv.is_overdue)

    def test_customer_terms_override_the_default(self):
        self.customer.payment_terms_days = 7
        self.customer.save()
        inv = self._sell()
        self.assertEqual(inv.payment_terms_days, 7)

    def test_payload_terms_override_everything(self):
        inv = self._sell(payment_terms_days=3)
        self.assertEqual(inv.payment_terms_days, 3)

    def test_customer_zero_terms_means_due_today(self):
        self.customer.payment_terms_days = 0
        self.customer.save()
        inv = self._sell()
        self.assertEqual(inv.due_date, _local_day(inv))


class ZeroTenderTests(TermsBase):
    def test_nothing_tendered_records_no_payment(self):
        # The till sends the tendered amount; a customer paying nothing at the
        # counter is a credit sale, not a receipt of 0.00.
        inv = self._sell(payment={"method": "cash", "amount": "0"})
        self.assertEqual(inv.payments.count(), 0)
        self.assertEqual(inv.amount_due(), inv.total)
        listed = self.client.get("/api/invoices/", {"page": 1}).data["results"][0]
        self.assertEqual(listed["customer_name"], "Buyer")


class ProfileAndCustomerFieldTests(TermsBase):
    def test_company_default_is_editable_within_bounds(self):
        ok = self.client.patch(
            "/api/company/profile/", {"default_payment_terms_days": 45}, format="json"
        )
        self.assertEqual(ok.status_code, 200, ok.data)
        self.company.refresh_from_db()
        self.assertEqual(self.company.default_payment_terms_days, 45)
        bad = self.client.patch(
            "/api/company/profile/", {"default_payment_terms_days": 400}, format="json"
        )
        self.assertEqual(bad.status_code, 400)

    def test_customer_terms_round_trip(self):
        response = self.client.patch(
            f"/api/customers/{self.customer.pk}/", {"payment_terms_days": 14}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["payment_terms_days"], 14)


class BackfillTests(TermsBase):
    def test_backfill_recomputes_zero_term_credit_sales_only(self):
        credit = Invoice.objects.create(
            company=self.company, customer=self.customer, warehouse=self.wh, number=1,
            total=Decimal("50"), subtotal=Decimal("50"), payment_terms_days=0,
        )
        cash = Invoice.objects.create(
            company=self.company, customer=None, warehouse=self.wh, number=2,
            total=Decimal("5"), subtotal=Decimal("5"), payment_terms_days=0,
        )
        already = Invoice.objects.create(
            company=self.company, customer=self.customer, warehouse=self.wh, number=3,
            total=Decimal("5"), subtotal=Decimal("5"), payment_terms_days=10,
        )
        migration = import_module("sales.migrations.0015_backfill_due_dates")
        migration.backfill(apps, None)
        for inv in (credit, cash, already):
            inv.refresh_from_db()
        self.assertEqual(credit.payment_terms_days, 30)
        self.assertEqual(credit.due_date, credit.issued_at.date() + timedelta(days=30))
        self.assertEqual(cash.payment_terms_days, 0)
        self.assertEqual(already.payment_terms_days, 10)
        self.assertGreaterEqual(credit.due_date, timezone.localdate())
