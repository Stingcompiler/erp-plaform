"""Receiving: one expiry per lot, stripped lot numbers, archived and
non-stock products (inventory review 2026-09-24)."""
import uuid
from datetime import timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import Role, User
from core.models import ActivityLog
from inventory.models import Product, StockBatch, StockMovement, Warehouse
from org.models import Branch, Company
from purchasing.models import GoodsReceipt, Supplier


class ReceiptLotTests(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        branch = Branch.objects.create(company=self.company, name="Main")
        self.owner = User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123", company=self.company,
            role=Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS),
        )
        self.wh = Warehouse.objects.create(company=self.company, branch=branch, name="WH")
        self.supplier = Supplier.objects.create(company=self.company, name="Importer")
        self.drug = Product.objects.create(
            company=self.company, sku="MED", name="Syrup", track_batches=True,
            cost_price=Decimal("2"),
        )
        self.jan = timezone.localdate() + timedelta(days=120)
        self.feb = timezone.localdate() + timedelta(days=150)
        self.client.force_authenticate(self.owner)

    def _line(self, product=None, lot="L1", expiry=None):
        line = {"product": (product or self.drug).pk, "quantity": "5", "unit_cost": "2.00"}
        if lot is not None:
            line["lot_number"] = lot
        if expiry is not None:
            line["expiry_date"] = expiry.isoformat()
        return line

    def _receive(self, *lines):
        return self.client.post(reverse("receiving-create"), {
            "supplier": self.supplier.pk, "warehouse": self.wh.pk, "lines": list(lines),
        }, format="json")

    def _push(self, *lines):
        cu = str(uuid.uuid4())
        response = self.client.post(reverse("sync-push"), {
            "device_id": "dev-1", "batch_uuid": str(uuid.uuid4()),
            "operations": [{"op_type": "goods_receipt", "client_uuid": cu, "payload": {
                "client_uuid": cu, "supplier": self.supplier.pk, "warehouse": self.wh.pk,
                "lines": list(lines),
            }}],
        }, format="json")
        self.assertIn(response.status_code, (200, 201), response.content)
        return response.data["results"][0]

    def test_lot_number_is_stripped(self):
        self.assertEqual(self._receive(self._line(lot=" L1 ", expiry=self.jan)).status_code, 201)
        self.assertEqual(self._receive(self._line(lot="L1", expiry=self.jan)).status_code, 201)
        self.assertEqual(StockBatch.objects.get().lot_number, "L1")
        self.assertEqual(self.drug.on_hand(), Decimal("10"))

    def test_a_different_expiry_for_a_known_lot_is_refused_live(self):
        self._receive(self._line(expiry=self.jan))
        response = self._receive(self._line(expiry=self.feb))
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("lines", response.data)
        self.assertEqual(GoodsReceipt.objects.count(), 1)
        self.assertEqual(StockBatch.objects.get().expiry_date, self.jan)

    def test_a_different_expiry_replayed_from_a_device_lands_and_is_audited(self):
        self._receive(self._line(expiry=self.jan))
        result = self._push(self._line(expiry=self.feb))
        self.assertEqual(result["status"], "applied", result)
        self.assertEqual(StockBatch.objects.get().expiry_date, self.jan)
        self.assertEqual(self.drug.on_hand(), Decimal("10"))
        self.assertTrue(ActivityLog.objects.filter(action="lot_expiry_conflict").exists())

    def test_a_lot_first_received_without_expiry_takes_the_later_one(self):
        self._receive(self._line())
        self.assertIsNone(StockBatch.objects.get().expiry_date)
        self.assertEqual(self._receive(self._line(expiry=self.feb)).status_code, 201)
        self.assertEqual(StockBatch.objects.get().expiry_date, self.feb)

    def test_archived_and_non_stock_products_are_not_received_live(self):
        old = Product.objects.create(
            company=self.company, sku="OLD", name="Old", is_active=False,
        )
        bag = Product.objects.create(
            company=self.company, sku="BAG", name="Bag", is_stock_tracked=False,
        )
        for product in (old, bag):
            response = self._receive(self._line(product=product, lot=None))
            self.assertEqual(response.status_code, 400, response.data)
            self.assertIn("lines", response.data)
        self.assertFalse(StockMovement.objects.exists())
        result = self._push(self._line(product=old, lot=None))
        self.assertEqual(result["status"], "applied", result)
        self.assertTrue(ActivityLog.objects.filter(
            action="sync_stock_rule_bypassed", metadata__rule="archived",
        ).exists())
