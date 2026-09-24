"""Stock adjustments reach net profit; inventory valuation as of a date.

A count that finds 10 units missing at a cost of 100 is a loss of 1,000.
Before, it moved the stock but never the profit, so net profit read 1,000
too high. Valuation was always "today" whatever the report's dates said.
"""
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import Role, User
from finance.models import Expense
from finance.metrics import operating_summary
from inventory.costing import company_totals
from inventory.models import Product, StockAdjustment, StockMovement, Warehouse
from org.models import Branch, Company
from returns.models import SalesReturn, SalesReturnLine
from sales.models import Customer, Invoice, InvoiceLine


class StockAdjustmentProfitTests(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Shrink")
        self.branch = Branch.objects.create(company=self.company, name="Main")
        self.owner = User.objects.create_user(
            email="owner@shrink.test", password="Asecurepass123", company=self.company,
            role=Role.objects.create(name="Business Owner", scope_level="business"),
        )
        self.officer = User.objects.create_user(
            email="officer@shrink.test", password="Asecurepass123", company=self.company,
            branch=self.branch,
            role=Role.objects.create(name="Inventory Officer", scope_level="branch"),
        )
        self.client.force_authenticate(self.owner)
        self.product = Product.objects.create(
            company=self.company, name="Widget", sku="W", cost_price=100, sale_price=150,
        )
        self.wh = Warehouse.objects.create(company=self.company, branch=self.branch, name="W")
        StockMovement.objects.create(
            company=self.company, product=self.product, warehouse=self.wh,
            movement_type=StockMovement.PURCHASE_IN, quantity=50, unit_cost=100,
        )
        customer = Customer.objects.create(company=self.company, name="C")
        self.invoice = Invoice.objects.create(
            company=self.company, warehouse=self.wh, customer=customer, number=1,
            subtotal=3000, total=3000,
        )
        self.line = InvoiceLine.objects.create(
            invoice=self.invoice, product=self.product, quantity=20, unit_price=150,
            line_subtotal=3000, line_total=3000,
        )
        StockMovement.objects.create(
            company=self.company, product=self.product, warehouse=self.wh,
            movement_type=StockMovement.SALE_OUT, quantity=-20, unit_cost=100,
            reference_type="Invoice", reference_id=str(self.invoice.pk),
        )
        Expense.objects.create(
            company=self.company, category="Rent", amount=200, date=timezone.localdate(),
        )
        # Revenue 3,000 − COGS 2,000 − rent 200 = 800 before any adjustment.

    def screens(self, **params):
        income = self.client.get("/api/reports/income-statement/", params).data
        summary = self.client.get(reverse("expense-summary"), params).data
        kpis = self.client.get("/api/reports/cfo-kpis/", params).data
        return income, summary, kpis

    def count(self, counted):
        """Counted by the officer, approved by the owner (the real path)."""
        self.client.force_authenticate(self.officer)
        created = self.client.post(
            reverse("stockcount-list"),
            {"warehouse": self.wh.id,
             "lines": [{"product": self.product.id, "counted_quantity": str(counted)}]},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        count_id = created.data["id"]
        self.client.post(reverse("stockcount-submit", args=[count_id]))
        self.client.force_authenticate(self.owner)
        approved = self.client.post(reverse("stockcount-approve", args=[count_id]))
        self.assertEqual(approved.status_code, 200, approved.data)

    def test_a_count_shortage_lowers_net_profit_and_the_screens_agree(self):
        self.count(20)  # 30 on the books, 20 on the shelf: 10 missing × 100
        income, summary, kpis = self.screens()
        self.assertEqual(income["stock_adjustments"], "1000.00")
        self.assertEqual(income["gross_profit"], "1000.00")  # COGS untouched
        self.assertEqual(income["cogs"], "2000.00")
        self.assertEqual(income["net_profit"], "-200.00")  # 800 − 1,000
        self.assertEqual(summary["net"], income["net_profit"])
        self.assertEqual(summary["expenses"], "200.00")  # not an expense
        self.assertEqual(kpis["profitability"]["net_profit"], income["net_profit"])
        self.assertEqual(kpis["profitability"]["stock_adjustments"], "1000.00")
        dashboard = self.client.get(reverse("dashboard")).data
        self.assertEqual(dashboard["sections"]["finance"]["net"], "-200.00")
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"
        csv = self.client.get("/api/reports/income-statement/", {"format": "csv"}).content
        self.assertIn(b'"Stock adjustments (counts, damage)",1000.00', csv)

    def test_a_surplus_raises_net_profit(self):
        self.count(33)  # three more than the books
        income, summary, _ = self.screens()
        self.assertEqual(income["stock_adjustments"], "-300.00")
        self.assertEqual(income["net_profit"], "1100.00")
        self.assertEqual(summary["net"], "1100.00")

    def test_every_method_charges_the_shortage(self):
        self.count(20)
        for method in ("standard", "average", "fifo"):
            data = operating_summary(self.company.pk, method=method)
            self.assertEqual(data["stock_adjustments"], "1000.00", method)
            self.assertEqual(data["net_profit"], "-200.00", method)

    def test_fifo_charges_the_layer_the_loss_came_from(self):
        # 30 left at 100; 10 more arrive at 130; FIFO loses the oldest first.
        StockMovement.objects.create(
            company=self.company, product=self.product, warehouse=self.wh,
            movement_type=StockMovement.PURCHASE_IN, quantity=10, unit_cost=130,
        )
        self.client.post(reverse("stockadjustment-list"), {
            "product": self.product.id, "warehouse": self.wh.id, "quantity": "-35",
            "reason_code": "theft", "reason": "Break-in",
        }, format="json")
        totals = company_totals(self.company.pk, method="fifo")
        self.assertEqual(totals["adjustments"], Decimal("3650"))  # 30×100 + 5×130
        self.assertEqual(totals["valuation"], Decimal("650"))  # 5×130 left

    def test_a_damage_write_off_counts_at_its_cost_snapshot(self):
        response = self.client.post(reverse("stockadjustment-list"), {
            "product": self.product.id, "warehouse": self.wh.id, "quantity": "-2",
            "reason_code": "damage", "reason": "Dropped",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        # A later cost change does not rewrite the loss already booked.
        self.product.cost_price = 400
        self.product.save(update_fields=["cost_price"])
        self.assertEqual(operating_summary(self.company.pk)["stock_adjustments"], "200.00")

    def test_opening_stock_is_not_a_gain(self):
        response = self.client.post(reverse("stockadjustment-list"), {
            "product": self.product.id, "warehouse": self.wh.id, "quantity": "100",
            "reason_code": "opening", "reason": "Stock we already had",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        StockMovement.objects.create(
            company=self.company, product=self.product, warehouse=self.wh,
            movement_type=StockMovement.ADJUSTMENT, quantity=5, unit_cost=100,
            reference_type="seed_demo",
        )
        for method in ("standard", "average", "fifo"):
            self.assertEqual(
                operating_summary(self.company.pk, method=method)["stock_adjustments"],
                "0.00", method,
            )

    def test_only_adjustments_in_the_period_count(self):
        last_month = timezone.now() - timedelta(days=40)
        movement = StockMovement.objects.create(
            company=self.company, product=self.product, warehouse=self.wh,
            movement_type=StockMovement.ADJUSTMENT, quantity=-4, unit_cost=100,
            reference_type="StockAdjustment", created_at=last_month,
        )
        StockAdjustment.objects.create(
            company=self.company, product=self.product, warehouse=self.wh,
            quantity=-4, reason_code="damage", reason="Old", movement=movement,
        )
        today = timezone.localdate().isoformat()
        income, _, _ = self.screens(start=today, end=today)
        self.assertEqual(income["stock_adjustments"], "0.00")
        income, _, _ = self.screens()
        self.assertEqual(income["stock_adjustments"], "400.00")

    def test_a_scrapped_return_is_not_counted_twice(self):
        # Scrapping moves no stock: its cost stays in COGS (the revenue is
        # reversed, the cost of the sale is not), so it is not an adjustment.
        sales_return = SalesReturn.objects.create(
            company=self.company, invoice=self.invoice, customer=self.invoice.customer,
            created_by=self.owner,
        )
        SalesReturnLine.objects.create(
            sales_return=sales_return, invoice_line=self.line, product=self.product,
            quantity=2, disposition=SalesReturnLine.SCRAPPED,
            written_off_value=Decimal("200"),
        )
        income, _, _ = self.screens()
        self.assertEqual(income["stock_adjustments"], "0.00")
        self.assertEqual(income["cogs"], "2000.00")
        self.assertEqual(income["revenue"], "2700.00")


class ValuationAsOfTests(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="AsOf")
        self.branch = branch = Branch.objects.create(company=self.company, name="Main")
        self.owner = User.objects.create_user(
            email="owner@asof.test", password="Asecurepass123", company=self.company,
            role=Role.objects.create(name="Business Owner", scope_level="business"),
        )
        self.client.force_authenticate(self.owner)
        self.product = Product.objects.create(
            company=self.company, name="Oil", sku="O", cost_price=10,
        )
        wh = Warehouse.objects.create(company=self.company, branch=branch, name="W")
        self.week_ago = timezone.now() - timedelta(days=7)
        StockMovement.objects.create(
            company=self.company, product=self.product, warehouse=wh,
            movement_type=StockMovement.PURCHASE_IN, quantity=5, unit_cost=8,
            created_at=self.week_ago,
        )
        # Received today — after an as-of date of three days ago.
        StockMovement.objects.create(
            company=self.company, product=self.product, warehouse=wh,
            movement_type=StockMovement.PURCHASE_IN, quantity=20, unit_cost=12,
        )

    def valuation(self, **params):
        response = self.client.get("/api/reports/inventory-valuation/", params)
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def test_stock_received_after_the_date_is_excluded(self):
        as_of = (timezone.localdate() - timedelta(days=3)).isoformat()
        expected = {"standard": "50", "average": "40", "fifo": "40"}
        for method, value in expected.items():
            data = self.valuation(method=method, as_of=as_of)
            self.assertEqual(data["as_of"], as_of)
            self.assertEqual(Decimal(data["total_value"]), Decimal(value), method)
            self.assertEqual(Decimal(data["items"][0]["on_hand"]), Decimal("5"), method)

    def test_a_branch_reader_sees_their_branch_as_of_the_date(self):
        other = Branch.objects.create(company=self.company, name="Other")
        other_wh = Warehouse.objects.create(company=self.company, branch=other, name="X")
        StockMovement.objects.create(
            company=self.company, product=self.product, warehouse=other_wh,
            movement_type=StockMovement.PURCHASE_IN, quantity=7, unit_cost=10,
            created_at=self.week_ago,
        )
        manager = User.objects.create_user(
            email="bm@asof.test", password="Asecurepass123", company=self.company,
            branch=self.branch,
            role=Role.objects.create(name="Branch Manager", scope_level="branch"),
        )
        self.client.force_authenticate(manager)
        as_of = (timezone.localdate() - timedelta(days=3)).isoformat()
        data = self.valuation(as_of=as_of)
        self.assertEqual(Decimal(data["items"][0]["on_hand"]), Decimal("5"))
        self.assertEqual(Decimal(data["total_value"]), Decimal("50"))

    def test_without_a_date_it_is_today(self):
        data = self.valuation(method="fifo")
        self.assertIsNone(data["as_of"])
        self.assertEqual(Decimal(data["total_value"]), Decimal("280"))  # 5×8 + 20×12

    def test_an_invalid_date_is_refused(self):
        response = self.client.get(
            "/api/reports/inventory-valuation/", {"as_of": "2026-02-30"}
        )
        self.assertEqual(response.status_code, 400)
