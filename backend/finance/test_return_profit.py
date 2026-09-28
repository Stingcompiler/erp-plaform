"""Review F06: a full return after a cost rise must not book a profit.

Sell one unit that cost 60, raise the product's cost to 90, take the unit
back: the period earned nothing and cost nothing, under every costing
method. Reading today's 90 for the return leg (with 60 for the sale) would
show COGS of -30 — profit out of thin air.
"""
from decimal import Decimal

from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import Role, User
from finance.metrics import operating_summary
from inventory.models import Product, StockMovement, Warehouse
from org.models import Branch, Company
from returns.models import SalesReturnLine
from sales.models import Customer, Invoice


class FullReturnProfitTests(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        self.branch = Branch.objects.create(company=self.company, name="Main")
        owner = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        self.owner = User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123",
            company=self.company, role=owner,
        )
        self.wh = Warehouse.objects.create(company=self.company, branch=self.branch, name="WH")
        self.product = Product.objects.create(
            company=self.company, sku="SKU1", name="Widget",
            cost_price=Decimal("60"), sale_price=Decimal("100"),
        )
        StockMovement.objects.create(
            company=self.company, product=self.product, warehouse=self.wh,
            movement_type=StockMovement.PURCHASE_IN, quantity=Decimal("5"),
            unit_cost=Decimal("60"),
        )
        self.customer = Customer.objects.create(company=self.company, name="Ahmed")
        self.client.force_authenticate(self.owner)

    def test_full_return_after_a_cost_rise_nets_to_zero_under_every_method(self):
        sale = self.client.post(
            reverse("pos-checkout"),
            {"warehouse": self.wh.pk, "customer": self.customer.pk,
             "lines": [{"product": self.product.pk, "quantity": "1"}],
             "payment": {"method": "cash", "amount": "100.00"}},
            format="json",
        )
        self.assertEqual(sale.status_code, 201, sale.data)
        invoice = Invoice.objects.get(pk=sale.data["id"])
        before = operating_summary(self.company.pk, method="standard")
        self.assertEqual(Decimal(before["revenue"]), Decimal("100"))
        self.assertEqual(Decimal(before["cogs"]), Decimal("60"))

        self.product.cost_price = Decimal("90")
        self.product.save(update_fields=["cost_price"])
        returned = self.client.post(
            reverse("salesreturn-list"),
            {"invoice": invoice.pk, "lines": [
                {"invoice_line": invoice.lines.get().pk, "product": self.product.pk,
                 "quantity": "1"}
            ]},
            format="json",
        )
        self.assertEqual(returned.status_code, 201, returned.data)
        line = SalesReturnLine.objects.get()
        restocked = self.client.post(
            reverse("salesreturn-list") + f"{returned.data['id']}/disposition/",
            {"decisions": [{"line_id": line.pk, "action": "restock", "warehouse": self.wh.pk}]},
            format="json",
        )
        self.assertEqual(restocked.status_code, 200, restocked.data)

        for method in ("standard", "average", "fifo"):
            with self.subTest(method=method):
                summary = operating_summary(self.company.pk, method=method)
                self.assertEqual(Decimal(summary["revenue"]), Decimal("0"))
                self.assertEqual(Decimal(summary["cogs"]), Decimal("0"))
                self.assertEqual(Decimal(summary["gross_profit"]), Decimal("0"))
                self.assertEqual(Decimal(summary["net_profit"]), Decimal("0"))
        # The income statement endpoint reads the same figures.
        report = self.client.get(reverse("report-income-statement"), {"method": "fifo"})
        self.assertEqual(report.status_code, 200, report.data)
        self.assertEqual(Decimal(report.data["cogs"]), Decimal("0"))
