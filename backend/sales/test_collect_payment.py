"""The collection flow the debt ledger drives: a customer's open invoices,
oldest first, and per-invoice payments that the API caps at the balance.
"""

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from sales.models import Invoice, Payment
from sales.test_receivables_sql import BalanceBase


class OpenInvoiceListTests(BalanceBase):
    def setUp(self):
        super().setUp()
        c = self.customers[0]
        self.old = self._invoice(c, "100", 1)
        self.new = self._invoice(c, "50", 2)
        self.paid = self._invoice(c, "30", 3)
        self.other = self._invoice(self.customers[1], "999", 4)
        Invoice.objects.filter(pk=self.old.pk).update(
            issued_at=timezone.now() - timedelta(days=10)
        )
        Payment.objects.create(
            company=self.company, invoice=self.paid, method=Payment.CASH,
            amount=Decimal("30"), recorded_by=self.owner,
        )

    def test_open_invoices_for_one_customer_oldest_first(self):
        response = self.client.get(
            "/api/invoices/", {"customer": self.customers[0].pk, "open": 1}
        )
        self.assertEqual(response.status_code, 200)
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual([r["id"] for r in rows], [self.old.pk, self.new.pk])
        self.assertEqual(Decimal(str(rows[0]["amount_due"])), Decimal("100"))

    def test_customer_filter_alone_lists_every_invoice_of_that_customer(self):
        response = self.client.get("/api/invoices/", {"customer": self.customers[0].pk})
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual({r["id"] for r in rows}, {self.old.pk, self.new.pk, self.paid.pk})

    def test_partial_then_full_settlement_through_the_payment_api(self):
        first = self.client.post(
            "/api/payments/",
            {"invoice": self.old.pk, "method": "cash", "amount": "60",
             "client_uuid": "11111111-1111-4111-8111-111111111111"},
            format="json",
        )
        self.assertEqual(first.status_code, 201, first.data)
        self.old.refresh_from_db()
        self.assertEqual(self.old.amount_due(), Decimal("40"))
        self.assertEqual(self.old.status, "partially_paid")

        too_much = self.client.post(
            "/api/payments/",
            {"invoice": self.old.pk, "method": "cash", "amount": "41",
             "client_uuid": "22222222-2222-4222-8222-222222222222"},
            format="json",
        )
        self.assertEqual(too_much.status_code, 400)

        rest = self.client.post(
            "/api/payments/",
            {"invoice": self.old.pk, "method": "cash", "amount": "40",
             "client_uuid": "33333333-3333-4333-8333-333333333333"},
            format="json",
        )
        self.assertEqual(rest.status_code, 201, rest.data)
        self.old.refresh_from_db()
        self.assertEqual(self.old.status, "paid")
        # It has left the collection list.
        response = self.client.get(
            "/api/invoices/", {"customer": self.customers[0].pk, "open": 1}
        )
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual([r["id"] for r in rows], [self.new.pk])
