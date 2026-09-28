"""A payment (or a credit note, refund or void) must reach every device.

Review F18: pull keyed invoices on ``received_at`` — the moment the invoice
row arrived — and never pulled payments, so an invoice paid after a device
last synced stayed "unpaid" in that device's mirror until something else
reloaded it.
"""
from datetime import timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from returns.models import CreditNote
from sales.models import Customer, Invoice, Payment, Refund
from sync.tests import SyncBase


class PullSettledInvoicesTests(SyncBase):
    def _invoice(self, number, days_ago):
        invoice = Invoice.objects.create(
            company=self.company, branch=self.branch, warehouse=self.wh, number=number,
            customer=self.customer, subtotal=Decimal("100"), total=Decimal("100"),
        )
        stamp = timezone.now() - timedelta(days=days_ago)
        Invoice.objects.filter(pk=invoice.pk).update(received_at=stamp, updated_at=stamp)
        return invoice

    def setUp(self):
        super().setUp()
        self.customer = Customer.objects.create(company=self.company, name="Ahmed")
        self.paid = self._invoice(1, 10)
        self.untouched = self._invoice(2, 10)
        self.credited = self._invoice(3, 10)
        self.voided = self._invoice(4, 10)
        first = self.client.get(reverse("sync-pull"))
        self.assertEqual(first.status_code, 200)
        self.assertEqual(len(first.data["changes"]["invoices"]), 4)
        self.cursor = first.data["cursor"]

    def _pull(self):
        response = self.client.get(reverse("sync-pull"), {"since": self.cursor})
        self.assertEqual(response.status_code, 200, response.data)
        return {row["number"]: row for row in response.data["changes"]["invoices"]}

    def test_a_payment_re_pulls_the_invoice_with_its_new_balance(self):
        Payment.objects.create(
            company=self.company, invoice=self.paid, method="cash", amount=Decimal("100"),
        )
        rows = self._pull()
        self.assertEqual(sorted(rows), [1])
        self.assertEqual(Decimal(rows[1]["amount_due"]), Decimal("0"))
        self.assertEqual(rows[1]["status"], "paid")

    def test_a_credit_note_and_its_refund_re_pull_the_invoice(self):
        note = CreditNote.objects.create(
            company=self.company, customer=self.customer, invoice=self.credited,
            amount=Decimal("40"),
        )
        rows = self._pull()
        self.assertEqual(sorted(rows), [3])
        self.assertEqual(Decimal(rows[3]["amount_due"]), Decimal("60"))
        self.cursor = self.client.get(
            reverse("sync-pull"), {"since": self.cursor}
        ).data["cursor"]
        Refund.objects.create(
            company=self.company, credit_note=note, method="cash", amount=Decimal("40"),
        )
        rows = self._pull()
        self.assertEqual(sorted(rows), [3])
        self.assertEqual(Decimal(rows[3]["amount_due"]), Decimal("100"))

    def test_a_void_re_pulls_the_invoice_and_nothing_else(self):
        void = self.client.post(
            reverse("invoice-void", args=[self.voided.pk]), {"reason": "wrong customer"},
            format="json",
        )
        self.assertEqual(void.status_code, 200, void.data)
        rows = self._pull()
        self.assertEqual(sorted(rows), [4])
        self.assertEqual(rows[4]["status"], "void")

    def test_nothing_is_re_pulled_when_nothing_changed(self):
        self.assertEqual(self._pull(), {})

    def test_a_backdated_offline_payment_still_reaches_the_delta(self):
        """The marker is server time: an offline till's payment recorded
        two days ago (business time) arrives now, and every other device's
        next delta pull must carry it. Stamping the payment's own time on
        the invoice put the marker behind the cursor."""
        from sales.payments import record_payment

        record_payment(
            self.paid, amount=Decimal("100"), method="cash", recorded_by=self.user,
            recorded_at=timezone.now() - timedelta(days=2),
        )
        rows = self._pull()
        self.assertEqual(sorted(rows), [1])
        self.assertEqual(rows[1]["status"], "paid")
