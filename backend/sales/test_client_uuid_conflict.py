"""A sale's idempotency key names ONE sale.

Two till tabs restored the same autosaved draft and so the same
`client_uuid`; the second tab's different sale was answered with the first
tab's invoice and silently never recorded. A replay with the same body is
still answered with the original invoice; a different body is refused."""

import uuid

from django.urls import reverse
from rest_framework import status

from inventory.models import StockMovement
from sales.idempotency import CLIENT_UUID_CONFLICT, checkout_fingerprint
from sales.models import Invoice
from sales.tests import SalesBase


class ClientUuidConflictTests(SalesBase):
    def test_identical_replay_returns_the_original_invoice(self):
        cu = uuid.uuid4()
        first = self.checkout(client_uuid=cu, payment={"method": "cash", "amount": "200.00"})
        self.assertEqual(first.status_code, status.HTTP_201_CREATED, first.content)
        self.assertTrue(Invoice.objects.get(pk=first.data["id"]).client_body_hash)
        again = self.checkout(client_uuid=cu, payment={"method": "cash", "amount": "200"})
        self.assertEqual(again.status_code, status.HTTP_200_OK, again.content)
        self.assertEqual(again.data["id"], first.data["id"])

    def test_same_key_with_a_different_sale_is_refused(self):
        cu = uuid.uuid4()
        first = self.checkout(client_uuid=cu, payment={"method": "cash", "amount": "200.00"})
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        other = self.checkout(
            client_uuid=cu, qty="3", payment={"method": "cash", "amount": "300.00"}
        )
        self.assertEqual(other.status_code, status.HTTP_409_CONFLICT, other.content)
        self.assertEqual(other.data["code"], CLIENT_UUID_CONFLICT)
        self.assertEqual(Invoice.objects.count(), 1)
        self.assertEqual(StockMovement.objects.filter(movement_type="sale_out").count(), 1)

    def test_a_different_payment_is_a_different_sale(self):
        cu = uuid.uuid4()
        self.checkout(client_uuid=cu, payment={"method": "cash", "amount": "200.00"})
        other = self.checkout(client_uuid=cu, payment={"method": "cash", "amount": "50.00"})
        self.assertEqual(other.status_code, status.HTTP_409_CONFLICT)

    def test_invoices_from_before_the_fingerprint_still_replay(self):
        cu = uuid.uuid4()
        first = self.checkout(client_uuid=cu, payment={"method": "cash", "amount": "200.00"})
        Invoice.objects.filter(pk=first.data["id"]).update(client_body_hash="")
        other = self.checkout(client_uuid=cu, qty="3")
        self.assertEqual(other.status_code, status.HTTP_200_OK)
        self.assertEqual(other.data["id"], first.data["id"])

    def test_a_synced_sale_keeps_its_fingerprint(self):
        cu = str(uuid.uuid4())
        payload = {
            "client_uuid": cu,
            "warehouse": self.wh_a.id,
            "customer": self.customer.id,
            "lines": [{"product": self.product.id, "quantity": "2"}],
            "payment": {"method": "cash", "amount": "200.00"},
        }
        pushed = self.client.post(reverse("sync-push"), {
            "batch_uuid": str(uuid.uuid4()),
            "operations": [{"op_type": "pos_checkout", "client_uuid": cu, "payload": payload}],
        }, format="json")
        self.assertEqual(pushed.status_code, status.HTTP_201_CREATED, pushed.content)
        invoice = Invoice.objects.get(client_uuid=cu)
        self.assertEqual(invoice.client_body_hash, checkout_fingerprint(payload))
        other = self.checkout(client_uuid=cu, qty="5")
        self.assertEqual(other.status_code, status.HTTP_409_CONFLICT)


class FingerprintTests(SalesBase):
    def test_times_and_number_formats_do_not_matter(self):
        a = {"warehouse": 1, "lines": [{"product": 2, "quantity": "3", "unit_price": "2.5"}],
             "occurred_at": "2026-01-01T00:00:00Z", "payment": {"method": "cash", "amount": "7.5"}}
        b = {"warehouse": "1", "lines": [{"product": "2", "quantity": 3.0, "unit_price": "2.50"}],
             "occurred_at": "2026-02-02T00:00:00Z", "sent_at": "2026-02-02T00:00:01Z",
             "payments": [{"method": "cash", "amount": "7.50"}]}
        self.assertEqual(checkout_fingerprint(a), checkout_fingerprint(b))

    def test_lines_matter(self):
        a = {"warehouse": 1, "lines": [{"product": 2, "quantity": "3"}]}
        b = {"warehouse": 1, "lines": [{"product": 2, "quantity": "4"}]}
        self.assertNotEqual(checkout_fingerprint(a), checkout_fingerprint(b))
