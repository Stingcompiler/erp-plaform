from datetime import timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import Role, User
from inventory.models import Product, StockBatch, StockMovement, Warehouse
from org.models import Branch, Company
from sales.models import Customer


class FefoAtSaleTests(APITestCase):
    """A batch-tracked product leaves the shelf soonest-expiry-first, never
    from an expired lot, and a scanned lot is honoured."""

    def setUp(self):
        self.company = Company.objects.create(name="Pharma")
        branch = Branch.objects.create(company=self.company, name="Main")
        owner = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        self.user = User.objects.create_user(
            email="owner@pharma.test", password="passw0rd123", company=self.company, role=owner
        )
        self.wh = Warehouse.objects.create(company=self.company, branch=branch, name="WH")
        self.product = Product.objects.create(
            company=self.company, sku="AMOX", name="Amoxicillin",
            sale_price=Decimal("10"), cost_price=Decimal("4"), track_batches=True,
        )
        today = timezone.now().date()
        self.late = self._lot("L-LATE", today + timedelta(days=300), 10)
        self.soon = self._lot("L-SOON", today + timedelta(days=30), 5)
        self.expired = self._lot("L-EXP", today - timedelta(days=1), 50)
        # Sales on account need a named debtor (see POSCheckoutSerializer);
        # tests that leave a balance sell to this account customer.
        self.customer = Customer.objects.create(company=self.company, name="Account customer")
        self.client.force_authenticate(self.user)

    def _lot(self, lot, expiry, qty):
        batch = StockBatch.objects.create(
            company=self.company, product=self.product, lot_number=lot, expiry_date=expiry
        )
        StockMovement.objects.create(
            company=self.company, product=self.product, warehouse=self.wh, batch=batch,
            movement_type=StockMovement.PURCHASE_IN, quantity=qty, unit_cost=Decimal("4"),
        )
        return batch

    def _sell(self, qty, batch=None):
        line = {"product": self.product.id, "quantity": str(qty)}
        if batch is not None:
            line["batch"] = batch.id
        return self.client.post(
            reverse("pos-checkout"),
            {"warehouse": self.wh.id, "customer": self.customer.id, "lines": [line]},
            format="json",
        )

    def _out(self):
        return {
            (m.batch.lot_number if m.batch_id else None): -m.quantity
            for m in StockMovement.objects.filter(movement_type=StockMovement.SALE_OUT)
        }

    def test_soonest_expiry_leaves_first_and_expired_is_skipped(self):
        response = self._sell(7)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(self._out(), {"L-SOON": Decimal("5"), "L-LATE": Decimal("2")})
        self.assertEqual(self.product.on_hand(batch=self.soon), Decimal("0"))
        self.assertEqual(self.product.on_hand(batch=self.late), Decimal("8"))
        self.assertEqual(self.product.on_hand(batch=self.expired), Decimal("50"))

    def test_scanned_lot_is_drawn_first(self):
        response = self._sell(3, batch=self.late)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(self._out(), {"L-LATE": Decimal("3")})

    def test_shortfall_becomes_untracked_remainder_not_a_blocked_sale(self):
        response = self._sell(20)
        self.assertEqual(response.status_code, 201, response.data)
        out = self._out()
        self.assertEqual(out["L-SOON"], Decimal("5"))
        self.assertEqual(out["L-LATE"], Decimal("10"))
        self.assertEqual(out[None], Decimal("5"))
        self.assertEqual(self.product.on_hand(warehouse=self.wh), Decimal("45"))  # 65 - 20

    def test_foreign_lot_is_refused(self):
        other = Product.objects.create(
            company=self.company, sku="OTHER", name="Other", sale_price=1, track_batches=True
        )
        lot = StockBatch.objects.create(company=self.company, product=other, lot_number="X")
        response = self._sell(1, batch=lot)
        self.assertEqual(response.status_code, 400)
        self.assertIn("batch", response.data)
