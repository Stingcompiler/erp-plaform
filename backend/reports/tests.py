from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Role, User
from inventory.models import Product, StockMovement, Warehouse
from org.models import Company
from purchasing.models import Bill, Supplier
from sales.models import Customer, Invoice, InvoiceLine


class ReportsBase(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        self.owner = Role.objects.create(
            name="Business Owner", scope_level=Role.SCOPE_BUSINESS
        )
        self.lpm = Role.objects.create(
            name="Landing Page Manager", scope_level=Role.SCOPE_BRANCH
        )
        self.user = User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123",
            company=self.company, role=self.owner,
        )
        self.wh = Warehouse.objects.create(company=self.company, name="Main")
        self.product = Product.objects.create(
            company=self.company, sku="SKU1", name="Widget",
            cost_price=Decimal("6.00"), sale_price=Decimal("10.00"),
        )
        # Stock in 20 units.
        StockMovement.objects.create(
            company=self.company, product=self.product, warehouse=self.wh,
            movement_type=StockMovement.PURCHASE_IN, quantity=Decimal("20"),
        )
        # An invoice with one line: 5 units @ 10 = 50 subtotal.
        self.customer = Customer.objects.create(company=self.company, name="C1")
        self.invoice = Invoice.objects.create(
            company=self.company, customer=self.customer, warehouse=self.wh,
            number=1, subtotal=Decimal("50"), total=Decimal("50"),
        )
        InvoiceLine.objects.create(
            invoice=self.invoice, product=self.product, quantity=Decimal("5"),
            unit_price=Decimal("10"), line_subtotal=Decimal("50"),
            line_total=Decimal("50"),
        )
        StockMovement.objects.create(
            company=self.company, product=self.product, warehouse=self.wh,
            movement_type=StockMovement.SALE_OUT, quantity=Decimal("-5"),
        )
        r = self.client.post(
            reverse("auth-login"), {"email": "owner@alpha.test", "password": "passw0rd123"}
        )
        assert r.status_code == 200, r.content


class SalesReportTests(ReportsBase):
    def test_sales_summary_matches_invoices(self):
        resp = self.client.get(reverse("report-sales-summary"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["totals"]["invoice_count"], 1)
        self.assertEqual(Decimal(resp.data["totals"]["total"]), Decimal("50"))

    def test_sales_by_product(self):
        resp = self.client.get(reverse("report-sales-by-product"))
        row = resp.data[0]
        self.assertEqual(row["sku"], "SKU1")
        self.assertEqual(Decimal(row["units"]), Decimal("5"))
        self.assertEqual(Decimal(row["revenue"]), Decimal("50"))

    def test_sales_by_product_csv(self):
        resp = self.client.get(reverse("report-sales-by-product"), {"format": "csv"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/csv")
        self.assertIn("SKU1", resp.content.decode())


class ValuationAndProfitTests(ReportsBase):
    def test_inventory_valuation(self):
        resp = self.client.get(reverse("report-inventory-valuation"))
        # on_hand = 20 - 5 = 15; value = 15 * 6 = 90.
        self.assertEqual(Decimal(resp.data["total_value"]), Decimal("90"))
        item = resp.data["items"][0]
        self.assertEqual(Decimal(item["on_hand"]), Decimal("15"))
        self.assertEqual(Decimal(item["value"]), Decimal("90"))

    def test_profit_summary(self):
        resp = self.client.get(reverse("report-profit-summary"))
        # revenue 50; cogs = 5 units * 6 = 30; gross = 20.
        self.assertEqual(Decimal(resp.data["revenue"]), Decimal("50"))
        self.assertEqual(Decimal(resp.data["cogs_standard_cost"]), Decimal("30"))
        self.assertEqual(Decimal(resp.data["gross_profit"]), Decimal("20"))


class AgingTests(ReportsBase):
    def test_ar_aging_reflects_outstanding(self):
        resp = self.client.get(reverse("report-ar-aging"))
        self.assertEqual(len(resp.data), 1)
        row = resp.data[0]
        self.assertEqual(Decimal(row["total"]), Decimal("50"))

    def test_ap_aging_reflects_outstanding(self):
        supplier = Supplier.objects.create(company=self.company, name="Acme")
        Bill.objects.create(company=self.company, supplier=supplier, total=Decimal("120"))
        resp = self.client.get(reverse("report-ap-aging"))
        self.assertEqual(Decimal(resp.data[0]["total"]), Decimal("120"))


class ReportsRBACTests(ReportsBase):
    def test_landing_page_manager_denied_reports(self):
        User.objects.create_user(
            email="lpm@alpha.test", password="passw0rd123",
            company=self.company, role=self.lpm,
        )
        c = self.client_class()
        c.post(reverse("auth-login"), {"email": "lpm@alpha.test", "password": "passw0rd123"})
        resp = c.get(reverse("report-sales-summary"))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_reports_are_company_scoped(self):
        # A second company's invoice must not appear in this company's report.
        other = Company.objects.create(name="Beta")
        Invoice.objects.create(
            company=other,
            warehouse=Warehouse.objects.create(company=other, name="BW"),
            number=1, subtotal=Decimal("999"), total=Decimal("999"),
        )
        resp = self.client.get(reverse("report-sales-summary"))
        self.assertEqual(Decimal(resp.data["totals"]["total"]), Decimal("50"))
