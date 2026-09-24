"""Sales fixes from the 2026-09-24 review: credit notes, collections, the
customer record, voids, orders and quotations, due dates."""

from datetime import timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from org.models import Branch
from returns.models import CreditNote
from sales.models import Invoice, Quotation, SalesOrder, SalesOrderLine
from sales.test_corrections import CorrectionBase


class SalesReviewTests(CorrectionBase):
    def test_a_sales_officer_cannot_issue_a_credit_note_from_nothing(self):
        self._as(self.cashier)
        response = self.client.post(reverse("creditnote-list"), {
            "customer": self.customer.id, "amount": "5000.00", "reason": "x",
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(CreditNote.objects.exists())
        self._as(self.owner)  # a manager still can (goodwill, corrections)
        ok = self.client.post(reverse("creditnote-list"), {
            "customer": self.customer.id, "amount": "50.00", "reason": "goodwill",
        }, format="json")
        self.assertEqual(ok.status_code, 201, ok.data)

    def test_a_credit_note_spent_as_store_credit_cannot_be_voided(self):
        self._as(self.owner)
        note = self.client.post(reverse("creditnote-list"), {
            "customer": self.customer.id, "amount": "100.00", "reason": "goodwill",
        }, format="json").data
        self._as(self.cashier)
        spent = self.client.post(reverse("pos-checkout"), {
            "warehouse": self.wh.id, "customer": self.customer.id,
            "lines": [{"product": self.product.id, "quantity": "1"}],
            "apply_credit": {"credit_note": note["id"], "amount": "100.00"},
        }, format="json")
        self.assertEqual(spent.status_code, 201, spent.data)
        self._as(self.owner)
        refused = self.client.post(
            reverse("creditnote-void", args=[note["id"]]), {"reason": "oops"}, format="json",
        )
        self.assertEqual(refused.status_code, 400)
        # ...and the statement closes at zero, not -100 (the note and the
        # payment it made used to count twice).
        statement = self.client.get(
            reverse("customer-debt-statement", args=[self.customer.id])
        ).data
        self.assertEqual(Decimal(statement["closing_balance"]), Decimal("0"))

    def test_voiding_after_a_refunded_note_refunds_only_what_is_owed(self):
        invoice = Invoice.objects.get(pk=self._sell(qty="1", paid="100.00").data["id"])
        shift = self._open_shift(self.owner)
        note = self.client.post(reverse("creditnote-list"), {
            "customer": self.customer.id, "invoice": invoice.id, "amount": "40.00",
            "reason": "price",
        }, format="json").data
        refunded = self.client.post(reverse("refund-list"), {
            "credit_note": note["id"], "amount": "40.00", "method": "cash", "shift": shift.id,
        }, format="json")
        self.assertEqual(refunded.status_code, 201, refunded.data)
        voided = self.client.post(
            reverse("invoice-void", args=[invoice.pk]),
            {"reason": "wrong item", "refund": {"method": "cash", "shift": shift.id}},
            format="json",
        )
        self.assertEqual(voided.status_code, 200, voided.data)
        self.assertEqual(shift.expected_cash(), Decimal("-100.00"))  # 40 + 60 back

    def test_a_branch_user_sees_only_their_branch_on_the_customer_record(self):
        other = Branch.objects.create(company=self.company, name="Other")
        Invoice.objects.create(
            company=self.company, branch=other, warehouse=self.wh, customer=self.customer,
            number=999, subtotal=Decimal("70"), total=Decimal("70"),
        )
        self._sell(qty="1")  # this branch: 100 owed
        self._as(self.cashier)
        data = self.client.get(reverse("customer-records", args=[self.customer.id])).data
        refs = [row.get("reference") for row in data["events"]]
        self.assertNotIn("INV-000999", refs)
        self.assertEqual(Decimal(data["customer"]["balance"]), Decimal("100.00"))

    def _order(self, qty="5"):
        order = SalesOrder.objects.create(
            company=self.company, customer=self.customer, branch=self.branch,
            status=SalesOrder.CONFIRMED, subtotal=Decimal("500"), total=Decimal("500"),
        )
        SalesOrderLine.objects.create(
            sales_order=order, product=self.product, quantity=Decimal(qty),
            unit_price=Decimal("100"), line_total=Decimal("100") * Decimal(qty),
        )
        return order

    def test_an_order_is_not_closed_by_a_sale_that_does_not_deliver_it(self):
        order = self._order("5")
        self._as(self.cashier)
        short = self.client.post(reverse("pos-checkout"), {
            "warehouse": self.wh.id, "customer": self.customer.id, "source_order": order.id,
            "lines": [{"product": self.product.id, "quantity": "1", "unit_price": "1.00"}],
        }, format="json")
        self.assertEqual(short.status_code, 400)
        order.refresh_from_db()
        self.assertEqual(order.status, SalesOrder.CONFIRMED)

    def test_quotes_and_orders_refuse_nonsense(self):
        self._as(self.owner)
        negative = self.client.post(reverse("quotation-list"), {
            "customer": self.customer.id,
            "lines": [{"product": self.product.id, "quantity": "-3", "unit_price": "100"}],
        }, format="json")
        self.assertEqual(negative.status_code, 400)
        created = self.client.post(reverse("salesorder-list"), {
            "customer": self.customer.id, "status": "fulfilled",
            "lines": [{"product": self.product.id, "quantity": "1", "unit_price": "100"}],
        }, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertNotEqual(created.data["status"], "fulfilled")
        quote = Quotation.objects.create(
            company=self.company, customer=self.customer, branch=self.branch,
            status=Quotation.SENT, valid_until=timezone.localdate() - timedelta(days=1),
        )
        expired = self.client.post(reverse("quotation-convert-to-order", args=[quote.id]))
        self.assertEqual(expired.status_code, 400)
        backwards = self.client.post(
            reverse("quotation-set-status", args=[quote.id]), {"status": "draft"}, format="json",
        )
        self.assertEqual(backwards.status_code, 400)

    def test_the_due_date_follows_the_company_calendar(self):
        self.company.timezone = "Africa/Khartoum"
        self.company.save(update_fields=["timezone"])
        # 23:30 UTC on the 1st is 01:30 on the 2nd in Khartoum.
        issued = timezone.now().replace(hour=23, minute=30, second=0, microsecond=0)
        invoice = Invoice.objects.create(
            company=self.company, branch=self.branch, warehouse=self.wh, customer=self.customer,
            number=77, subtotal=Decimal("1"), total=Decimal("1"), issued_at=issued,
        )
        self.assertEqual(invoice.due_date, (issued + timedelta(hours=2)).date())
