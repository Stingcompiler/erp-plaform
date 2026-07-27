import uuid
from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Role, User
from inventory.models import Product, StockMovement, Warehouse
from org.models import Company
from sales.models import Invoice
from sync.models import SyncBatch


class SyncBase(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        self.owner_role = Role.objects.create(
            name="Business Owner", scope_level=Role.SCOPE_BUSINESS
        )
        self.user = User.objects.create_user(
            email="a@alpha.test", password="passw0rd123",
            company=self.company, role=self.owner_role,
        )
        self.wh = Warehouse.objects.create(company=self.company, name="Main")
        self.product = Product.objects.create(
            company=self.company, sku="SKU1", name="Widget", sale_price=Decimal("10"),
        )
        r = self.client.post(
            reverse("auth-login"), {"email": "a@alpha.test", "password": "passw0rd123"}
        )
        assert r.status_code == 200, r.content

    def push(self, operations, batch_uuid=None):
        return self.client.post(
            reverse("sync-push"),
            {
                "device_id": "dev-1",
                "batch_uuid": str(batch_uuid or uuid.uuid4()),
                "operations": operations,
            },
            format="json",
        )

    def movement_op(self, cu, qty="5"):
        return {
            "op_type": "stock_movement",
            "client_uuid": str(cu),
            "payload": {
                "product": self.product.id, "warehouse": self.wh.id,
                "movement_type": "purchase_in", "quantity": qty,
            },
        }

    def checkout_op(self, cu):
        return {
            "op_type": "pos_checkout",
            "client_uuid": str(cu),
            "payload": {
                "client_uuid": str(cu),
                "warehouse": self.wh.id,
                "lines": [{"product": self.product.id, "quantity": "2"}],
                "payment": {"method": "cash", "amount": "20.00"},
            },
        }


class BatchApplyTests(SyncBase):
    def test_batch_applies_each_operation_once(self):
        resp = self.push([self.movement_op(uuid.uuid4()), self.checkout_op(uuid.uuid4())])
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        self.assertEqual(resp.data["summary"]["applied"], 2)
        self.assertEqual(StockMovement.objects.filter(movement_type="purchase_in").count(), 1)
        self.assertEqual(Invoice.objects.count(), 1)

    def test_replaying_whole_batch_is_noop(self):
        bu = uuid.uuid4()
        ops = [self.movement_op(uuid.uuid4())]
        r1 = self.push(ops, batch_uuid=bu)
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        r2 = self.push(ops, batch_uuid=bu)
        self.assertEqual(r2.status_code, status.HTTP_200_OK)
        self.assertTrue(r2.data["replay"])
        self.assertEqual(SyncBatch.objects.count(), 1)
        self.assertEqual(StockMovement.objects.count(), 1)

    def test_same_op_uuid_in_new_batch_is_duplicate(self):
        cu = uuid.uuid4()
        self.push([self.movement_op(cu)])
        resp = self.push([self.movement_op(cu)])  # new batch, same op uuid
        self.assertEqual(resp.data["summary"]["duplicate"], 1)
        self.assertEqual(resp.data["summary"]["applied"], 0)
        self.assertEqual(StockMovement.objects.count(), 1)

    def test_partial_failure_isolated(self):
        good = self.movement_op(uuid.uuid4())
        bad = {
            "op_type": "stock_movement",
            "client_uuid": str(uuid.uuid4()),
            "payload": {  # purchase_in must be positive -> validation error
                "product": self.product.id, "warehouse": self.wh.id,
                "movement_type": "purchase_in", "quantity": "-5",
            },
        }
        resp = self.push([good, bad])
        self.assertEqual(resp.data["summary"]["applied"], 1)
        self.assertEqual(resp.data["summary"]["error"], 1)
        # The good op still committed despite the bad one.
        self.assertEqual(StockMovement.objects.count(), 1)
        results = {r["index"]: r["status"] for r in resp.data["results"]}
        self.assertEqual(results[0], "applied")
        self.assertEqual(results[1], "error")

    def test_unknown_op_type_errors(self):
        resp = self.push([{"op_type": "nonsense", "payload": {}}])
        self.assertEqual(resp.data["results"][0]["status"], "error")


class SyncRBACTests(SyncBase):
    def test_role_without_module_access_op_forbidden(self):
        # An Inventory Officer may not push a POS checkout (sales write).
        inv_role = Role.objects.create(
            name="Inventory Officer", scope_level=Role.SCOPE_BRANCH
        )
        User.objects.create_user(
            email="inv@alpha.test", password="passw0rd123",
            company=self.company, role=inv_role,
        )
        c = self.client_class()
        c.post(reverse("auth-login"), {"email": "inv@alpha.test", "password": "passw0rd123"})
        resp = c.post(
            reverse("sync-push"),
            {"batch_uuid": str(uuid.uuid4()), "operations": [self.checkout_op(uuid.uuid4())]},
            format="json",
        )
        self.assertEqual(resp.data["results"][0]["status"], "error")
        self.assertEqual(Invoice.objects.count(), 0)


class SyncPullTests(SyncBase):
    def test_pull_returns_changes_for_readable_modules(self):
        resp = self.client.get(reverse("sync-pull"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("cursor", resp.data)
        self.assertIn("products", resp.data["changes"])
        # Product created in setUp shows up.
        skus = {p["sku"] for p in resp.data["changes"]["products"]}
        self.assertIn("SKU1", skus)

    def test_pull_since_future_returns_empty(self):
        resp = self.client.get(reverse("sync-pull"), {"since": "2999-01-01T00:00:00Z"})
        self.assertEqual(resp.data["changes"]["products"], [])

    def test_missing_batch_uuid_rejected(self):
        resp = self.client.post(
            reverse("sync-push"), {"operations": []}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
