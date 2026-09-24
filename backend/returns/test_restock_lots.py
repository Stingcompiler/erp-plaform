"""A restocked return goes back into the lots the sale drew from, not all
into the first one (inventory review 2026-09-24)."""
from datetime import timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import Role, User
from inventory.models import Product, StockBatch, StockMovement, Warehouse
from org.models import Branch, Company
from returns.models import SalesReturnLine
from sales.models import Customer, Invoice


class RestockAcrossLotsTests(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        branch = Branch.objects.create(company=self.company, name="Main")
        self.owner = User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123", company=self.company,
            role=Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS),
        )
        self.wh = Warehouse.objects.create(company=self.company, branch=branch, name="WH")
        self.product = Product.objects.create(
            company=self.company, sku="MED", name="Syrup", track_batches=True,
            cost_price=Decimal("2"), sale_price=Decimal("5"),
        )
        today = timezone.localdate()
        self.l1 = StockBatch.objects.create(
            company=self.company, product=self.product, lot_number="L1",
            expiry_date=today + timedelta(days=60),
        )
        self.l2 = StockBatch.objects.create(
            company=self.company, product=self.product, lot_number="L2",
            expiry_date=today + timedelta(days=200),
        )
        for lot, qty in ((self.l1, 3), (self.l2, 7)):
            StockMovement.objects.create(
                company=self.company, product=self.product, warehouse=self.wh, batch=lot,
                movement_type=StockMovement.PURCHASE_IN, quantity=Decimal(qty),
                unit_cost=Decimal("2"),
            )
        self.client.force_authenticate(self.owner)
        customer = Customer.objects.create(company=self.company, name="Ahmed")
        sale = self.client.post(reverse("pos-checkout"), {
            "warehouse": self.wh.pk, "customer": customer.pk,
            "lines": [{"product": self.product.pk, "quantity": "10"}],
            "payment": {"method": "cash", "amount": "50.00"},
        }, format="json")
        self.assertEqual(sale.status_code, 201, sale.data)
        self.invoice = Invoice.objects.get(pk=sale.data["id"])
        # FEFO drew L1 x3 then L2 x7.
        self.assertEqual(self.product.on_hand(batch=self.l1), 0)
        self.assertEqual(self.product.on_hand(batch=self.l2), 0)

    def _return_and_restock(self, qty):
        created = self.client.post(reverse("salesreturn-list"), {
            "invoice": self.invoice.pk,
            "lines": [{"invoice_line": self.invoice.lines.get().pk,
                       "product": self.product.pk, "quantity": str(qty)}],
        }, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        line = SalesReturnLine.objects.get(sales_return_id=created.data["id"])
        done = self.client.post(
            reverse("salesreturn-disposition", args=[created.data["id"]]),
            {"decisions": [{"line_id": line.pk, "action": "restock", "warehouse": self.wh.pk}]},
            format="json",
        )
        self.assertEqual(done.status_code, 200, done.data)
        line.refresh_from_db()
        return line

    def test_full_return_restores_each_lot_exactly(self):
        line = self._return_and_restock(10)
        self.assertEqual(self.product.on_hand(batch=self.l1), Decimal("3"))
        self.assertEqual(self.product.on_hand(batch=self.l2), Decimal("7"))
        self.assertEqual(line.restock_movement.unit_cost, Decimal("2"))
        self.assertEqual(
            StockMovement.objects.filter(
                reference_type="SalesReturn", movement_type=StockMovement.SALES_RETURN_IN,
            ).count(),
            2,
        )

    def test_partial_returns_fill_the_last_drawn_lot_first(self):
        first = self._return_and_restock(4)
        self.assertEqual(first.batch, self.l2)
        self.assertEqual(self.product.on_hand(batch=self.l2), Decimal("4"))
        self.assertEqual(self.product.on_hand(batch=self.l1), Decimal("0"))
        self._return_and_restock(6)
        self.assertEqual(self.product.on_hand(batch=self.l2), Decimal("7"))
        self.assertEqual(self.product.on_hand(batch=self.l1), Decimal("3"))
