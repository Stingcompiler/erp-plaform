import uuid
from decimal import Decimal

from django.urls import reverse
from rest_framework import status

from integration.base import IntegrationBase
from sync.models import SyncBatch


class OfflineSyncEndToEndTests(IntegrationBase):
    """A client drains a queue of mixed operations, then re-syncs safely."""

    def setUp(self):
        self.company = self.make_company("Alpha")
        self.client = self.owner_client(self.company, "owner@alpha.test")
        self.wh = self.warehouse(self.company)
        self.product_obj = self.product(self.company, cost="6", price="10")

    def _batch(self, batch_uuid):
        return {
            "batch_uuid": str(batch_uuid),
            "device_id": "till-1",
            "operations": [
                {
                    "op_type": "stock_movement",
                    "client_uuid": str(uuid.uuid4()),
                    "payload": {
                        "product": self.product_obj.id, "warehouse": self.wh.id,
                        "movement_type": "adjustment", "quantity": "50",
                    },
                },
                {
                    "op_type": "pos_checkout",
                    "client_uuid": str(uuid.uuid4()),
                    "payload": {
                        "warehouse": self.wh.id,
                        "lines": [{"product": self.product_obj.id, "quantity": "5"}],
                        "payment": {"method": "cash", "amount": "50"},
                    },
                },
            ],
        }

    def test_queue_applies_then_replays_idempotently_then_pulls(self):
        bu = uuid.uuid4()
        # First push applies everything.
        r1 = self.client.post(reverse("sync-push"), self._batch(bu), format="json")
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED, r1.content)
        self.assertEqual(r1.data["summary"]["applied"], 2)
        self.assertEqual(self.on_hand(self.client, self.product_obj.id), Decimal("45"))

        # Replaying the same batch is a no-op.
        r2 = self.client.post(reverse("sync-push"), self._batch(bu), format="json")
        self.assertEqual(r2.status_code, status.HTTP_200_OK)
        self.assertTrue(r2.data["replay"])
        self.assertEqual(SyncBatch.objects.count(), 1)
        self.assertEqual(self.on_hand(self.client, self.product_obj.id), Decimal("45"))

        # Delta pull returns the company's changed records.
        pull = self.client.get(reverse("sync-pull"))
        self.assertEqual(pull.status_code, 200)
        self.assertIn("products", pull.data["changes"])
        skus = {p["sku"] for p in pull.data["changes"]["products"]}
        self.assertIn(self.product_obj.sku, skus)

    def test_same_operation_uuid_across_batches_is_deduped(self):
        cu = str(uuid.uuid4())
        op = {
            "op_type": "stock_movement",
            "client_uuid": cu,
            "payload": {
                "product": self.product_obj.id, "warehouse": self.wh.id,
                "movement_type": "adjustment", "quantity": "7",
            },
        }
        self.client.post(
            reverse("sync-push"),
            {"batch_uuid": str(uuid.uuid4()), "operations": [op]},
            format="json",
        )
        second = self.client.post(
            reverse("sync-push"),
            {"batch_uuid": str(uuid.uuid4()), "operations": [op]},
            format="json",
        )
        self.assertEqual(second.data["summary"]["duplicate"], 1)
        self.assertEqual(self.on_hand(self.client, self.product_obj.id), Decimal("7"))
