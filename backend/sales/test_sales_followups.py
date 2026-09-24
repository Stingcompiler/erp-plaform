"""Sales follow-ups: customer balances in SQL, refunds checked under the
invoice lock, and a void that gives store credit back as credit."""

from decimal import Decimal

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from returns.models import CreditNote
from sales.models import Customer, Invoice, Refund
from sales.querysets import with_ar_balance
from sales.test_corrections import CorrectionBase


class FollowupBase(CorrectionBase):
    def _sale(self, customer, qty="2", cash=None, credit=None, user=None):
        self._as(user or self.cashier)
        body = {
            "warehouse": self.wh.id, "customer": customer.id,
            "lines": [{"product": self.product.id, "quantity": qty}],
        }
        if cash is not None:
            body["payment"] = {"method": "cash", "amount": cash}
        if credit is not None:
            body["apply_credit"] = {"credit_note": credit[0].pk, "amount": credit[1]}
        response = self.client.post(reverse("pos-checkout"), body, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return Invoice.objects.get(pk=response.data["id"])

    def _return_all(self, invoice):
        line = invoice.lines.get()
        self._as(self.owner)
        returned = {
            "invoice_line": line.pk, "product": self.product.pk, "quantity": str(line.quantity),
        }
        response = self.client.post(
            reverse("salesreturn-list"),
            {"invoice": invoice.pk, "lines": [returned]},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        return CreditNote.objects.get(invoice=invoice, sales_return__isnull=False)

    def _note(self, invoice, amount):
        self._as(self.owner)
        response = self.client.post(
            reverse("creditnote-list"),
            {"customer": invoice.customer_id, "invoice": invoice.pk, "amount": amount,
             "reason": "price correction"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        return CreditNote.objects.get(pk=response.data["id"])

    def _refund(self, note, amount, shift):
        self._as(self.owner)
        return self.client.post(
            reverse("refund-list"),
            {"credit_note": note.pk, "method": "cash", "amount": amount, "shift": shift.pk},
            format="json",
        )

    def _void(self, invoice, refund=None):
        self._as(self.owner)
        body = {"reason": "wrong sale"}
        if refund is not None:
            body["refund"] = refund
        return self.client.post(reverse("invoice-void", args=[invoice.pk]), body, format="json")


class CustomerBalanceInSqlTests(FollowupBase):
    def _mixed_book(self):
        shift = self._open_shift(self.owner)
        bader = Customer.objects.create(company=self.company, name="Bader")
        Customer.objects.create(company=self.company, name="Celia")  # no invoices
        # Ahmed: a returned paid sale (credit), part refunded, part spent as
        # store credit on a second sale; a credit sale later voided; a
        # partly paid sale with a price correction.
        first = self._sale(self.customer, cash="200.00")
        note = self._return_all(first)
        self.assertEqual(self._refund(note, "50.00", shift).status_code, 201)
        self._sale(self.customer, credit=(note, "100.00"), cash="50.00")
        unpaid = self._sale(self.customer, qty="1")
        self.assertEqual(self._void(unpaid).status_code, 200)
        partly = self._sale(self.customer, cash="50.00")
        self._note(partly, "30.00")
        # Bader: a paid sale voided with its refund, and an open credit sale.
        paid = self._sale(bader, qty="1", cash="100.00")
        self.assertEqual(
            self._void(paid, {"method": "cash", "shift": shift.pk}).status_code, 200
        )
        self._sale(bader, qty="1")
        return shift

    def test_annotated_balance_equals_the_model_method(self):
        self._mixed_book()
        rows = with_ar_balance(Customer.objects.filter(company=self.company))
        self.assertEqual(rows.count(), 3)
        for row in rows:
            with self.subTest(customer=row.name):
                self.assertEqual(row.ar_balance_sql, row.ar_balance())
        balances = {row.name: row.ar_balance_sql for row in rows}
        # 200 - 200 paid - 200 note + 50 refund + 100 spent elsewhere = -50;
        # 200 - 100 credit - 50 cash = 50; the voided sale 0;
        # 200 - 50 paid - 30 note = 120.
        self.assertEqual(balances["Ahmed"], Decimal("120.00"))
        self.assertEqual(balances["Bader"], Decimal("100.00"))
        self.assertEqual(balances["Celia"], Decimal("0"))

    def test_list_and_sync_pull_serve_the_same_balance(self):
        self._mixed_book()
        self._as(self.owner)
        listed = self.client.get(reverse("customer-list")).data
        listed = listed["results"] if isinstance(listed, dict) else listed
        pulled = self.client.get(reverse("sync-pull")).data["changes"]["customers"]
        for source in (listed, pulled):
            for row in source:
                customer = Customer.objects.get(pk=row["id"])
                with self.subTest(customer=customer.name):
                    self.assertEqual(Decimal(str(row["ar_balance"])), customer.ar_balance())

    def test_customer_list_queries_do_not_grow_with_invoices(self):
        self._sale(self.customer, cash="50.00")
        self._as(self.owner)
        with CaptureQueriesContext(connection) as few:
            self.assertEqual(self.client.get(reverse("customer-list")).status_code, 200)
        shift = self._open_shift(self.owner)
        for _i in range(6):
            invoice = self._sale(self.customer, cash="50.00")
            self._refund(self._note(invoice, "180.00"), "30.00", shift)
        self._as(self.owner)
        with CaptureQueriesContext(connection) as many:
            response = self.client.get(reverse("customer-list"))
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual(Decimal(str(rows[0]["ar_balance"])), self.customer.ar_balance())
        self.assertEqual(len(many.captured_queries), len(few.captured_queries))


class RefundUnderInvoiceLockTests(FollowupBase):
    def test_second_note_cannot_refund_more_than_was_paid(self):
        # 200 sale, 100 paid; two notes on it (150 + 50) put 100 in credit.
        invoice = self._sale(self.customer, cash="100.00")
        first = self._note(invoice, "150.00")
        second = self._note(invoice, "50.00")
        self.assertEqual(invoice.amount_due(), Decimal("-100.00"))
        shift = self._open_shift(self.owner)
        self.assertEqual(self._refund(first, "80.00", shift).status_code, 201)
        # Only 20 of the money paid is left, whichever note it comes from.
        too_much = self._refund(second, "30.00", shift)
        self.assertEqual(too_much.status_code, 400, too_much.data)
        self.assertIn("amount", too_much.data)
        self.assertEqual(self._refund(second, "20.00", shift).status_code, 201)
        self.assertEqual(invoice.amount_due(), Decimal("0"))
        self.assertEqual(Refund.objects.filter(credit_note__invoice=invoice).count(), 2)


class VoidWithStoreCreditTests(FollowupBase):
    def _paid_with_credit(self):
        # A returned 100 sale leaves 100 of credit; a new 100 sale takes 60
        # of it plus 40 cash.
        earlier = self._sale(self.customer, qty="1", cash="100.00")
        note = self._return_all(earlier)
        invoice = self._sale(self.customer, qty="1", credit=(note, "60.00"), cash="40.00")
        self.assertEqual(invoice.amount_due(), Decimal("0"))
        return invoice, note

    def _available_credit(self):
        self._as(self.owner)
        return Decimal(self.client.get(f"/api/customers/{self.customer.pk}/credit/").data["total"])

    def test_void_refunds_the_money_and_gives_the_credit_back(self):
        invoice, note = self._paid_with_credit()
        self.assertEqual(self._available_credit(), Decimal("40.00"))
        self._as(self.owner)
        preview = self.client.get(reverse("invoice-void-preview", args=[invoice.pk])).data
        self.assertEqual(preview, {"refund": "40.00", "credit": "60.00"})

        refused = self._void(invoice)
        self.assertEqual(refused.status_code, 400)
        self.assertIn("40.00", str(refused.data["refund"]))

        shift = self._open_shift(self.owner)
        voided = self._void(invoice, {"method": "cash", "shift": shift.pk})
        self.assertEqual(voided.status_code, 200, voided.data)
        void_note = CreditNote.objects.get(invoice=invoice)
        self.assertEqual(Refund.objects.get(credit_note=void_note).amount, Decimal("40.00"))
        self.assertEqual(shift.expected_cash(), Decimal("-40.00"))
        # The 60 of store credit is the customer's again: 40 left on the old
        # note plus 60 on the void note.
        self.assertEqual(void_note.remaining_refundable(), Decimal("60.00"))
        self.assertEqual(self._available_credit(), Decimal("100.00"))

        # And it spends like any credit.
        again = self._sale(self.customer, qty="1", credit=(void_note, "60.00"), cash="40.00")
        self.assertEqual(again.amount_due(), Decimal("0"))
        self.assertEqual(void_note.remaining_refundable(), Decimal("0"))

    def test_void_of_a_sale_paid_only_with_credit_needs_no_refund(self):
        earlier = self._sale(self.customer, qty="1", cash="100.00")
        note = self._return_all(earlier)
        invoice = self._sale(self.customer, qty="1", credit=(note, "100.00"))
        voided = self._void(invoice)
        self.assertEqual(voided.status_code, 200, voided.data)
        self.assertFalse(Refund.objects.filter(credit_note__invoice=invoice).exists())
        self.assertEqual(self._available_credit(), Decimal("100.00"))

    def test_cash_voids_still_leave_no_credit_behind(self):
        invoice = self._sale(self.customer, qty="1", cash="100.00")
        shift = self._open_shift(self.owner)
        self.assertEqual(
            self._void(invoice, {"method": "cash", "shift": shift.pk}).status_code, 200
        )
        self.assertEqual(self._available_credit(), Decimal("0"))
        self.assertEqual(
            CreditNote.objects.get(invoice=invoice).remaining_refundable(), Decimal("0")
        )
