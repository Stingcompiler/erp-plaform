"""Opening balances are documents: they show up as debt, not as sales."""

from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import Role, User
from inventory.models import Warehouse
from org.models import Branch, Company
from purchasing.models import Bill, Supplier
from sales.models import Customer, Invoice


class OpeningBalanceTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        self.branch = Branch.objects.create(company=self.company, name="Main")
        Warehouse.objects.create(company=self.company, branch=self.branch, name="W")
        owner = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        clerk = Role.objects.create(name="Branch Manager", scope_level=Role.SCOPE_BRANCH)
        self.owner = User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123", company=self.company,
            role=owner, branch=self.branch,
        )
        self.clerk = User.objects.create_user(
            email="clerk@alpha.test", password="passw0rd123", company=self.company,
            role=clerk, branch=self.branch,
        )
        self.customer = Customer.objects.create(company=self.company, name="Buyer")
        self.supplier = Supplier.objects.create(company=self.company, name="Acme")
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def test_customer_opening_balance_is_debt_but_not_revenue(self):
        response = self.client.post(
            f"/api/customers/{self.customer.pk}/opening_balance/",
            {"amount": "750.00", "as_of": "2026-01-01", "note": "Ledger carried over"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        invoice = Invoice.objects.get(pk=response.data["id"])
        self.assertTrue(invoice.is_opening_balance)
        self.assertEqual(invoice.due_date.isoformat(), "2026-01-01")
        self.assertEqual(self.customer.ar_balance(), Decimal("750.00"))
        summary = self.client.get("/api/reports/sales-summary/", {"start": "2026-01-01"})
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.data["totals"]["invoice_count"], 0)
        self.assertEqual(Decimal(summary.data["totals"]["total"]), Decimal("0"))

    def test_one_per_customer_and_approver_only(self):
        self.client.post(
            f"/api/customers/{self.customer.pk}/opening_balance/", {"amount": "10"}, format="json",
        )
        again = self.client.post(
            f"/api/customers/{self.customer.pk}/opening_balance/", {"amount": "10"}, format="json",
        )
        self.assertEqual(again.status_code, 400)
        self.client.force_authenticate(self.clerk)
        refused = self.client.post(
            f"/api/customers/{self.customer.pk}/opening_balance/", {"amount": "10"}, format="json",
        )
        self.assertEqual(refused.status_code, 403)
        self.assertEqual(refused.data["detail"].code, "permission_denied")

    def test_supplier_opening_balance_is_payable_but_not_a_purchase(self):
        response = self.client.post(
            f"/api/suppliers/{self.supplier.pk}/opening_balance/",
            {"amount": "1200", "as_of": "2026-02-01"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        bill = Bill.objects.get(pk=response.data["id"])
        self.assertTrue(bill.is_opening_balance)
        self.assertEqual(self.supplier.ap_balance(), Decimal("1200.00"))
        summary = self.client.get("/api/reports/purchases-summary/", {"start": "2026-01-01"})
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.data["bill_count"], 0)

    def test_future_date_and_bad_amount_refused(self):
        bad = self.client.post(
            f"/api/customers/{self.customer.pk}/opening_balance/",
            {"amount": "abc"}, format="json",
        )
        self.assertEqual(bad.status_code, 400)
        future = self.client.post(
            f"/api/customers/{self.customer.pk}/opening_balance/",
            {"amount": "5", "as_of": "2999-01-01"}, format="json",
        )
        self.assertEqual(future.status_code, 400)
