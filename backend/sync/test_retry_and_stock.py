"""Temporary failures are retried; offline stock figures stay fresh.

A deadlock or a dropped database connection used to come back as a final
"error": the till stopped sending the sale and offered the cashier to
discard it, although the same request would have gone through a minute
later. And the offline catalogue's on_hand never changed after the first
pull (a sale does not touch the product row) and was a company-wide total
while the till sells from one branch.
"""
import uuid
from decimal import Decimal
from unittest import mock

from django.db import OperationalError
from django.urls import reverse

from inventory.models import StockMovement, Warehouse
from org.models import Branch
from sales.models import Invoice
from sync.models import SyncBatch, SyncOperation
from sync.services import POSCheckoutSerializer
from sync.test_offline_robustness import OfflineBase


class RetryStatusTests(OfflineBase):
    def _op(self):
        cu = str(uuid.uuid4())
        return {
            "op_type": "pos_checkout", "client_uuid": cu,
            "payload": {
                "client_uuid": cu, "warehouse": self.wh.pk, "customer": self.customer.pk,
                "lines": [{"product": self.product.pk, "quantity": "1"}],
                "payment": {"method": "cash", "amount": "10.00"},
            },
        }

    def test_a_database_failure_is_retry_and_the_resumed_batch_applies_it(self):
        op = self._op()
        batch_uuid = uuid.uuid4()
        with mock.patch.object(
            POSCheckoutSerializer, "save", side_effect=OperationalError("deadlock detected")
        ):
            first = self._push([op], batch_uuid=batch_uuid)
        self.assertEqual(first.status_code, 201, first.data)
        result = first.data["results"][0]
        self.assertEqual(result["status"], "retry")
        self.assertNotIn("deadlock", result["error"])
        self.assertEqual(first.data["summary"]["retry"], 1)
        self.assertEqual(first.data["summary"]["error"], 0)
        self.assertFalse(Invoice.objects.exists())

        # The same batch again: the retry slot is not "done", so it is
        # processed again (not replayed from the stored answer).
        again = self._push([op], batch_uuid=batch_uuid)
        self.assertEqual(again.status_code, 200, again.data)
        self.assertTrue(again.data["replay"])
        self.assertEqual(again.data["results"][0]["status"], "applied")
        self.assertEqual(again.data["summary"]["applied"], 1)
        self.assertEqual(again.data["summary"]["retry"], 0)
        self.assertEqual(Invoice.objects.filter(client_uuid=op["client_uuid"]).count(), 1)
        self.assertEqual(SyncOperation.objects.get().status, "applied")

        # Now complete: a third push is a pure replay and applies nothing.
        third = self._push([op], batch_uuid=batch_uuid)
        self.assertEqual(third.data["results"][0]["status"], "applied")
        self.assertEqual(Invoice.objects.count(), 1)
        self.assertEqual(SyncBatch.objects.get().applied_count, 1)

    def test_a_validation_refusal_stays_an_error(self):
        op = self._op()
        op["payload"]["lines"] = []
        result = self._push([op]).data["results"][0]
        self.assertEqual(result["status"], "error")


class PullStockFreshnessTests(OfflineBase):
    def _pull(self, **params):
        response = self.client.get(reverse("sync-pull"), params)
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def _product_row(self, data):
        rows = [r for r in data["changes"]["products"] if r["id"] == self.product.pk]
        return rows[0] if rows else None

    def test_a_sale_after_the_cursor_resends_the_product_with_new_stock(self):
        StockMovement.objects.create(
            company=self.company, product=self.product, warehouse=self.wh,
            movement_type=StockMovement.ADJUSTMENT, quantity=Decimal("5"),
        )
        first = self._pull()
        self.assertEqual(Decimal(str(self._product_row(first)["on_hand"])), Decimal("5"))
        # Nothing changed: the product is not sent again.
        quiet = self._pull(since=first["cursor"])
        self.assertIsNone(self._product_row(quiet))

        response = self._checkout(uuid.uuid4())
        self.assertEqual(response.status_code, 201, response.data)
        second = self._pull(since=quiet["cursor"])
        row = self._product_row(second)
        self.assertIsNotNone(row, "a sold product must come back in the delta")
        self.assertEqual(Decimal(str(row["on_hand"])), Decimal("4"))

    def test_a_branch_user_gets_their_branch_quantity(self):
        other_branch = Branch.objects.create(company=self.company, name="Port Sudan")
        other_wh = Warehouse.objects.create(
            company=self.company, branch=other_branch, name="WH2"
        )
        for wh, qty in ((self.wh, "3"), (other_wh, "40")):
            StockMovement.objects.create(
                company=self.company, product=self.product, warehouse=wh,
                movement_type=StockMovement.ADJUSTMENT, quantity=Decimal(qty),
            )
        mine = self._product_row(self._pull())
        self.assertEqual(Decimal(str(mine["on_hand"])), Decimal("3"))

        self.client.force_authenticate(self.owner)
        everyone = self._product_row(self._pull())
        self.assertEqual(Decimal(str(everyone["on_hand"])), Decimal("43"))

    def test_movement_in_another_branch_does_not_resend_to_a_branch_till(self):
        other_branch = Branch.objects.create(company=self.company, name="Port Sudan")
        other_wh = Warehouse.objects.create(
            company=self.company, branch=other_branch, name="WH2"
        )
        first = self._pull()
        StockMovement.objects.create(
            company=self.company, product=self.product, warehouse=other_wh,
            movement_type=StockMovement.ADJUSTMENT, quantity=Decimal("7"),
        )
        self.assertIsNone(self._product_row(self._pull(since=first["cursor"])))
