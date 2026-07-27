import uuid
from decimal import Decimal

from django.urls import reverse
from rest_framework import status

from integration.base import IntegrationBase


class SellThroughLifecycleTests(IntegrationBase):
    """Receive -> sell -> return -> disposition, verified against the ledger."""

    def setUp(self):
        self.company = self.make_company("Alpha")
        self.client = self.owner_client(self.company, "owner@alpha.test")
        self.wh = self.warehouse(self.company)
        self.supplier_obj = self.supplier(self.company)
        self.product_obj = self.product(self.company, cost="6", price="10")

    def _receive(self, qty):
        return self.client.post(
            reverse("receiving-create"),
            {
                "client_uuid": uuid.uuid4().hex,
                "supplier": self.supplier_obj.id,
                "warehouse": self.wh.id,
                "lines": [
                    {"product": self.product_obj.id, "quantity": str(qty), "unit_cost": "6"}
                ],
            },
            format="json",
        )

    def _checkout(self, qty, amount):
        return self.client.post(
            reverse("pos-checkout"),
            {
                "client_uuid": uuid.uuid4().hex,
                "warehouse": self.wh.id,
                "lines": [{"product": self.product_obj.id, "quantity": str(qty)}],
                "payment": {"method": "cash", "amount": amount},
            },
            format="json",
        )

    def test_full_lifecycle_reconciles_stock_and_reports(self):
        # 1) Receive 100 (purchasing -> purchase_in movements)
        r = self._receive(100)
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.content)
        self.assertEqual(self.on_hand(self.client, self.product_obj.id), Decimal("100"))

        # 2) POS sale of 10 (sales -> sale_out + invoice + payment)
        checkout = self._checkout(10, "100")
        self.assertEqual(checkout.status_code, status.HTTP_201_CREATED, checkout.content)
        invoice_id = checkout.data["id"]
        self.assertEqual(self.on_hand(self.client, self.product_obj.id), Decimal("90"))

        # 3) Sales return of 4 — Rule #5: quarantined, NOT restocked yet
        ret = self.client.post(
            reverse("salesreturn-list"),
            {
                "client_uuid": uuid.uuid4().hex,
                "invoice": invoice_id,
                "reason": "damaged",
                "lines": [{"product": self.product_obj.id, "quantity": "4"}],
            },
            format="json",
        )
        self.assertEqual(ret.status_code, status.HTTP_201_CREATED, ret.content)
        return_id = ret.data["id"]
        line_id = ret.data["lines"][0]["id"]
        self.assertEqual(
            self.on_hand(self.client, self.product_obj.id), Decimal("90"),
            "returned stock must not silently re-enter sellable inventory",
        )

        # 4) Disposition: restock the 4 back into the warehouse
        disp = self.client.post(
            reverse("salesreturn-disposition", args=[return_id]),
            {"decisions": [{"line_id": line_id, "action": "restock", "warehouse": self.wh.id}]},
            format="json",
        )
        self.assertEqual(disp.status_code, status.HTTP_200_OK, disp.content)
        self.assertEqual(self.on_hand(self.client, self.product_obj.id), Decimal("94"))

        # 5) Reports reconcile with the ledger
        val = self.client.get(reverse("report-inventory-valuation"))
        item = next(i for i in val.data["items"] if i["product"] == self.product_obj.id)
        self.assertEqual(Decimal(item["on_hand"]), Decimal("94"))
        self.assertEqual(Decimal(item["value"]), Decimal("94") * Decimal("6"))

        summary = self.client.get(reverse("report-sales-summary"))
        self.assertGreaterEqual(summary.data["totals"]["invoice_count"], 1)

    def test_returned_stock_stays_quarantined_until_scrapped(self):
        self._receive(20)
        checkout = self._checkout(10, "100")
        invoice_id = checkout.data["id"]
        ret = self.client.post(
            reverse("salesreturn-list"),
            {
                "client_uuid": uuid.uuid4().hex,
                "invoice": invoice_id,
                "lines": [{"product": self.product_obj.id, "quantity": "3"}],
            },
            format="json",
        )
        line_id = ret.data["lines"][0]["id"]
        before = self.on_hand(self.client, self.product_obj.id)
        # Scrap disposition must NOT add stock back.
        self.client.post(
            reverse("salesreturn-disposition", args=[ret.data["id"]]),
            {"decisions": [{"line_id": line_id, "action": "scrap"}]},
            format="json",
        )
        self.assertEqual(self.on_hand(self.client, self.product_obj.id), before)
