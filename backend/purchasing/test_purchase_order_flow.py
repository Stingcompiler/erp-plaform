"""The purchase-order loop the UI now drives: raise, send, receive against
it, and read progress back per line.
"""

from decimal import Decimal

from django.urls import reverse
from rest_framework import status

from purchasing.models import PurchaseOrder
from purchasing.tests import PurchasingBase


class PurchaseOrderFlowTests(PurchasingBase):
    def _order(self):
        create = self.client.post(
            reverse("purchaseorder-list"),
            {
                "supplier": self.supplier.id,
                "lines": [
                    {"product": self.product.id, "quantity_ordered": "10", "unit_cost": "40"},
                    {"product": self.batch_product.id, "quantity_ordered": "4", "unit_cost": "10"},
                ],
            },
            format="json",
        )
        self.assertEqual(create.status_code, status.HTTP_201_CREATED, create.content)
        return create.data

    def test_order_lists_with_supplier_name_and_zero_progress(self):
        order = self._order()
        self.assertEqual(order["supplier_name"], "Acme")
        self.assertEqual(order["status"], "draft")
        line = next(row for row in order["lines"] if row["product"] == self.product.id)
        self.assertEqual(line["product_sku"], "SKU1")
        self.assertEqual(Decimal(line["received_quantity"]), Decimal("0"))
        self.assertEqual(Decimal(line["remaining_quantity"]), Decimal("10"))

    def test_status_moves_through_the_allowed_transitions(self):
        order = self._order()
        url = reverse("purchaseorder-set-status", args=[order["id"]])
        self.assertEqual(self.client.post(url, {"status": "sent"}, format="json").status_code, 200)
        confirmed = self.client.post(url, {"status": "confirmed"}, format="json")
        self.assertEqual(confirmed.status_code, 200)
        bad = self.client.post(url, {"status": "draft"}, format="json")
        self.assertEqual(bad.status_code, status.HTTP_400_BAD_REQUEST)

    def test_receiving_against_the_order_updates_progress_and_status(self):
        order = self._order()
        self.client.post(
            reverse("purchaseorder-set-status", args=[order["id"]]),
            {"status": "confirmed"}, format="json",
        )
        received = self.client.post(
            reverse("receiving-create"),
            {
                "supplier": self.supplier.id, "warehouse": self.wh_a.id,
                "purchase_order": order["id"],
                "lines": [{"product": self.product.id, "quantity": "6"}],
            },
            format="json",
        )
        self.assertEqual(received.status_code, status.HTTP_201_CREATED, received.content)
        detail = self.client.get(reverse("purchaseorder-detail", args=[order["id"]])).data
        self.assertEqual(detail["status"], PurchaseOrder.PARTIALLY_RECEIVED)
        line = next(row for row in detail["lines"] if row["product"] == self.product.id)
        self.assertEqual(Decimal(line["received_quantity"]), Decimal("6"))
        self.assertEqual(Decimal(line["remaining_quantity"]), Decimal("4"))
        # Over-receiving the remainder is refused.
        over = self.client.post(
            reverse("receiving-create"),
            {
                "supplier": self.supplier.id, "warehouse": self.wh_a.id,
                "purchase_order": order["id"],
                "lines": [{"product": self.product.id, "quantity": "5"}],
            },
            format="json",
        )
        self.assertEqual(over.status_code, status.HTTP_400_BAD_REQUEST)
