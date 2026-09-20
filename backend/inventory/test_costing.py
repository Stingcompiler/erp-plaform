from datetime import date, timedelta
from decimal import Decimal

from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import Role, User
from inventory.costing import compute
from inventory.models import Product, StockMovement, Warehouse
from org.models import Company


class CostingBase(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        self.wh = Warehouse.objects.create(company=self.company, name="Main")
        self.product = Product.objects.create(
            company=self.company, sku="SKU1", name="Widget",
            cost_price=Decimal("7"), sale_price=Decimal("12"),
        )
        # Two receipts at different costs, then a sale that spans both layers.
        self._move(StockMovement.PURCHASE_IN, "10", "5")
        self._move(StockMovement.PURCHASE_IN, "10", "8")
        self._move(StockMovement.SALE_OUT, "-15", None)

    def _move(self, mtype, qty, cost):
        return StockMovement.objects.create(
            company=self.company, product=self.product, warehouse=self.wh,
            movement_type=mtype, quantity=Decimal(qty),
            unit_cost=Decimal(cost) if cost is not None else None,
        )


class CostingEngineTests(CostingBase):
    def test_fifo(self):
        r = compute(self.product, "fifo")
        # 15 sold from [10@5, 10@8] -> 10*5 + 5*8 = 90; 5 left @8 -> 40.
        self.assertEqual(r["cogs"], Decimal("90"))
        self.assertEqual(r["valuation"], Decimal("40"))
        self.assertEqual(r["on_hand"], Decimal("5"))

    def test_weighted_average(self):
        r = compute(self.product, "average")
        # avg = 130/20 = 6.5; cogs = 15*6.5 = 97.5; valuation = 5*6.5 = 32.5.
        self.assertEqual(r["cogs"], Decimal("97.5"))
        self.assertEqual(r["valuation"], Decimal("32.5"))

    def test_standard(self):
        r = compute(self.product, "standard")
        # 15 * 7 = 105; 5 * 7 = 35.
        self.assertEqual(r["cogs"], Decimal("105"))
        self.assertEqual(r["valuation"], Decimal("35"))

    def test_window_excludes_out_of_range_sales_from_cogs(self):
        future = date.today() + timedelta(days=5)
        r = compute(self.product, "fifo", start=future)
        # No sales in the window -> zero COGS, but valuation is unchanged.
        self.assertEqual(r["cogs"], Decimal("0"))
        self.assertEqual(r["valuation"], Decimal("40"))


class CostingReportTests(CostingBase):
    def setUp(self):
        super().setUp()
        role = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123",
            company=self.company, role=role,
        )
        r = self.client.post(
            reverse("auth-login"), {
                "email": "owner@alpha.test",
                "password": "passw0rd123",
                "device_id": "TEST",
            }
        )
        assert r.status_code == 200, r.content

    def test_valuation_report_honours_method(self):
        fifo = self.client.get(reverse("report-inventory-valuation"), {"method": "fifo"})
        self.assertEqual(fifo.data["method"], "fifo")
        self.assertEqual(Decimal(fifo.data["total_value"]), Decimal("40"))

        avg = self.client.get(reverse("report-inventory-valuation"), {"method": "average"})
        self.assertEqual(Decimal(avg.data["total_value"]), Decimal("32.5"))

    def test_profit_report_honours_method(self):
        fifo = self.client.get(reverse("report-profit-summary"), {"method": "fifo"})
        self.assertEqual(fifo.data["method"], "fifo")
        self.assertEqual(Decimal(fifo.data["cogs"]), Decimal("90"))

    def test_default_method_is_standard(self):
        resp = self.client.get(reverse("report-profit-summary"))
        self.assertEqual(resp.data["method"], "standard")
        # cogs_standard_cost alias preserved for backward compatibility.
        self.assertIn("cogs_standard_cost", resp.data)
