"""Store credit: a customer's credit note pays a later invoice instead of
being handed back in cash. Money-neutral everywhere money is counted."""

from decimal import Decimal

from django.urls import reverse

from returns.models import CreditNote
from sales.models import Invoice, Payment
from sales.test_corrections import CorrectionBase


class StoreCreditTests(CorrectionBase):
    def _credit_of(self, paid):
        invoice = Invoice.objects.get(pk=self._sell(paid=paid).data["id"])
        line = invoice.lines.get()
        self._as(self.owner)
        self.client.post(
            reverse("salesreturn-list"),
            {"invoice": invoice.pk, "lines": [
                {"invoice_line": line.pk, "product": self.product.pk, "quantity": "2"}
            ]},
            format="json",
        )
        return invoice, CreditNote.objects.get(invoice=invoice)

    def test_pos_sale_paid_partly_with_credit(self):
        first, note = self._credit_of(paid="200.00")
        self.assertEqual(note.remaining_refundable(), Decimal("200.00"))
        credit = self.client.get(f"/api/customers/{self.customer.pk}/credit/")
        self.assertEqual(credit.data["total"], "200.00")
        self.assertEqual(credit.data["notes"][0]["id"], note.pk)

        # New sale of 200 (2 x 100): 150 from credit, 50 cash.
        self._as(self.cashier)
        response = self.client.post(reverse("pos-checkout"), {
            "warehouse": self.wh.id, "customer": self.customer.id,
            "lines": [{"product": self.product.id, "quantity": "2"}],
            "apply_credit": {"credit_note": note.pk, "amount": "150.00"},
            "payment": {"method": "cash", "amount": "50.00"},
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        second = Invoice.objects.get(pk=response.data["id"])
        self.assertEqual(second.amount_due(), Decimal("0"))
        self.assertEqual(second.payments.filter(method=Payment.STORE_CREDIT).count(), 1)
        # The credit moved: 50 left on the note, first invoice's balance reflects it.
        self.assertEqual(note.remaining_refundable(), Decimal("50.00"))
        self.assertEqual(first.amount_due(), Decimal("-50.00"))
        # Debt ledger agrees: customer in credit by 50, nothing owed.
        self._as(self.owner)
        summary = self.client.get(reverse("debt-summary")).data
        self.assertEqual(summary["credit_balance"], "50.00")
        self.assertEqual(summary["outstanding"], "0.00")
        # Cash-flow reports do not count the credit as money in.
        cash = self.client.get("/api/reports/cash-flow/").data
        self.assertEqual(Decimal(cash["inflows"]), Decimal("250.00"))
        # Nothing to verify for a credit application.
        worklist = self.client.get("/api/payments/", {"unverified": "1"}).data["results"]
        self.assertFalse(any(p["method"] == "credit" for p in worklist))

    def test_credit_cannot_exceed_or_cross_customers(self):
        _, note = self._credit_of(paid="200.00")
        self._as(self.cashier)
        too_much = self.client.post(reverse("pos-checkout"), {
            "warehouse": self.wh.id, "customer": self.customer.id,
            "lines": [{"product": self.product.id, "quantity": "3"}],
            "apply_credit": {"credit_note": note.pk, "amount": "250.00"},
        }, format="json")
        self.assertEqual(too_much.status_code, 400)
        self.assertIn("amount", too_much.data)
        other = self.client.post(reverse("pos-checkout"), {
            "warehouse": self.wh.id,
            "lines": [{"product": self.product.id, "quantity": "1"}],
            "apply_credit": {"credit_note": note.pk, "amount": "10.00"},
        }, format="json")
        self.assertEqual(other.status_code, 400)
        self.assertIn("credit_note", other.data)

    def test_collect_an_open_invoice_with_credit(self):
        _, note = self._credit_of(paid="200.00")
        open_invoice = Invoice.objects.get(pk=self._sell(paid=None).data["id"])
        self._as(self.owner)
        response = self.client.post(reverse("payment-list"), {
            "invoice": open_invoice.pk, "method": "credit", "credit_note": note.pk,
            "amount": "120.00", "client_uuid": "11111111-1111-4111-8111-111111111111",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(open_invoice.amount_due(), Decimal("80.00"))
        self.assertEqual(note.remaining_refundable(), Decimal("80.00"))
        # A cash refund of the rest is still allowed, but not more than that.
        shift = self._open_shift(self.owner)
        refund = self.client.post(reverse("refund-list"), {
            "credit_note": note.pk, "method": "cash", "amount": "100.00", "shift": shift.pk,
        }, format="json")
        self.assertEqual(refund.status_code, 400)
        statement = self.client.get(
            reverse("customer-debt-statement", args=[self.customer.pk])
        ).data
        self.assertIn("credit_applied", {row["type"] for row in statement["events"]})
