from datetime import timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import Role, User
from finance.models import Expense
from inventory.models import Product, Warehouse
from org.models import Company
from sales.models import Customer, Invoice, InvoiceLine, Payment
from returns.models import CreditNote


class MetricsConsistencyTests(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Metrics")
        self.role = Role.objects.create(name="Business Owner", scope_level="business")
        self.user = User.objects.create_user(email="metrics@example.test", company=self.company,
                                             role=self.role, password="Asecurepass123")
        self.client.force_authenticate(self.user)
        self.product = Product.objects.create(
            company=self.company, name="Widget", sku="W", cost_price=6)
        self.wh = Warehouse.objects.create(company=self.company, name="Main")
        self.customer = Customer.objects.create(company=self.company, name="Customer")
        self.invoice = Invoice.objects.create(
            company=self.company,
            warehouse=self.wh,
            customer=self.customer,
            number=1,
            subtotal=100,
            total=115,
            tax_amount=15,
            due_date=timezone.localdate() -
            timedelta(
                days=2))
        InvoiceLine.objects.create(invoice=self.invoice, product=self.product, quantity=10,
                                   unit_price=10, line_subtotal=100, line_tax=15, line_total=115)
        Expense.objects.create(
            company=self.company,
            category="Rent",
            amount=10,
            date=timezone.localdate())

    def test_summary_and_income_statement_agree_excluding_tax_void_and_other_company(self):
        void = Invoice.objects.create(
            company=self.company,
            warehouse=self.wh,
            number=2,
            subtotal=1000,
            total=1150,
            is_void=True)
        InvoiceLine.objects.create(invoice=void, product=self.product, quantity=100,
                                   unit_price=10, line_subtotal=1000, line_total=1150)
        other = Company.objects.create(name="Other")
        Expense.objects.create(
            company=other,
            category="Private",
            amount=8000,
            date=timezone.localdate())
        summary = self.client.get(reverse("expense-summary"))
        report = self.client.get("/api/reports/income-statement/")
        self.assertEqual(summary.status_code, 200, summary.data)
        self.assertEqual(summary.data["revenue"], "100.00")
        self.assertEqual(summary.data["cogs"], "60.00")
        self.assertEqual(summary.data["net"], "30.00")
        self.assertEqual(summary.data["net"], report.data["net_profit"])
        dashboard = self.client.get(reverse("dashboard"))
        self.assertEqual(dashboard.data["sections"]["finance"]["net"], "30.00")

    def test_date_filter_applies_to_both_sales_and_expenses(self):
        yesterday = str(timezone.localdate() - timedelta(days=1))
        data = self.client.get(reverse("expense-summary"), {"end": yesterday}).data
        self.assertEqual(Decimal(data["revenue"]), 0)
        self.assertEqual(Decimal(data["expenses"]), 0)
        self.assertEqual(self.client.get(reverse("expense-summary"),
                         {"start": "not-a-date"}).status_code, 400)
        self.assertEqual(self.client.get(reverse("expense-summary"),
                         {"start": "2026-09-12", "end": "2026-01-01"}).status_code, 400)

    def test_pagination_and_search_keep_older_expenses_accessible(self):
        Expense.objects.bulk_create([Expense(company=self.company, category="Travel", amount=i,
                                             date=timezone.localdate()) for i in range(55)])
        response = self.client.get(reverse("expense-list"),
                                   {"search": "Travel", "ordering": "-amount", "page": 2})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 55)
        self.assertEqual(len(response.data["results"]), 5)
        self.assertEqual(Decimal(response.data["results"][0]["amount"]), 4)

    def test_overdue_filter_accounts_for_multiple_payments_and_credits(self):
        Payment.objects.create(company=self.company, invoice=self.invoice, amount=30, method="cash")
        Payment.objects.create(company=self.company, invoice=self.invoice, amount=35, method="cash")
        CreditNote.objects.create(
            company=self.company,
            invoice=self.invoice,
            customer=self.customer,
            amount=20)
        self.assertEqual(self.client.get(reverse("invoice-list"),
                         {"overdue": "1"}).data["count"], 1)
        CreditNote.objects.create(
            company=self.company,
            invoice=self.invoice,
            customer=self.customer,
            amount=30)
        self.assertEqual(self.client.get(reverse("invoice-list"),
                         {"overdue": "1"}).data["count"], 0)
