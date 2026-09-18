"""The correction model: void, refund, note caps, AP netting, credit control.

Rule #9 says a financial record is never edited in place; a mistake is an
offsetting entry. Before this batch the system had no offsetting entry for
an invoice, a bill or a note, no document for money handed back, and a
customer's credit could be paid out twice or never. These tests pin the new
paths and the balances they produce.
"""
from decimal import Decimal

from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import Role, User
from core.models import ActivityLog
from finance.metrics import operating_summary
from inventory.models import Product, StockMovement, Warehouse
from org.models import Branch, Company
from purchasing.models import Bill, Supplier
from returns.models import CreditNote, DebitNote
from sales.models import CashDrawerMovement, CashShift, Customer, Invoice, Payment, Refund


class CorrectionBase(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        self.branch = Branch.objects.create(company=self.company, name="Main")
        self.owner_role = Role.objects.create(
            name="Business Owner", scope_level=Role.SCOPE_BUSINESS
        )
        self.sales_role = Role.objects.create(
            name="Sales Officer", scope_level=Role.SCOPE_BRANCH
        )
        self.owner = User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123",
            company=self.company, role=self.owner_role,
        )
        self.cashier = User.objects.create_user(
            email="till@alpha.test", password="passw0rd123",
            company=self.company, role=self.sales_role, branch=self.branch,
        )
        self.wh = Warehouse.objects.create(company=self.company, branch=self.branch, name="WH")
        self.product = Product.objects.create(
            company=self.company, sku="SKU1", name="Widget",
            sale_price=Decimal("100.00"), cost_price=Decimal("60.00"),
        )
        StockMovement.objects.create(
            company=self.company, product=self.product, warehouse=self.wh,
            movement_type=StockMovement.PURCHASE_IN, quantity=Decimal("10"),
            unit_cost=Decimal("60.00"),
        )
        self.customer = Customer.objects.create(company=self.company, name="Ahmed")

    def _as(self, user):
        self.client.force_authenticate(user)

    def _sell(self, qty="2", paid=None, customer=True, user=None):
        self._as(user or self.cashier)
        body = {
            "warehouse": self.wh.id,
            "lines": [{"product": self.product.id, "quantity": qty}],
        }
        if customer:
            body["customer"] = self.customer.id
        if paid is not None:
            body["payment"] = {"method": "cash", "amount": paid}
        return self.client.post(reverse("pos-checkout"), body, format="json")

    def _open_shift(self, user):
        self._as(user)
        response = self.client.post(
            reverse("cashshift-list"), {"opening_float": "0"}, format="json"
        )
        assert response.status_code == 201, response.data
        return CashShift.objects.get(pk=response.data["id"])


class VoidInvoiceTests(CorrectionBase):
    def test_void_reverses_stock_credits_the_sale_and_refunds_the_cash(self):
        sale = self._sell(paid="200.00")
        self.assertEqual(sale.status_code, 201, sale.data)
        invoice = Invoice.objects.get(pk=sale.data["id"])
        self.assertEqual(self.product.on_hand(), Decimal("8"))
        shift = self._open_shift(self.owner)

        response = self.client.post(
            reverse("invoice-void", args=[invoice.pk]),
            {"reason": "wrong customer", "refund": {"method": "cash", "shift": shift.pk}},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        invoice.refresh_from_db()
        self.assertTrue(invoice.is_void)
        self.assertEqual(invoice.amount_due(), Decimal("0"))
        self.assertEqual(self.product.on_hand(), Decimal("10"))
        back = StockMovement.objects.get(movement_type=StockMovement.SALES_RETURN_IN)
        self.assertEqual(back.unit_cost, Decimal("60.00"))
        note = CreditNote.objects.get(invoice=invoice)
        self.assertEqual(note.amount, Decimal("200.00"))
        refund = Refund.objects.get(credit_note=note)
        self.assertEqual(refund.amount, Decimal("200.00"))
        drawer = CashDrawerMovement.objects.get(refund=refund)
        self.assertEqual(drawer.amount, Decimal("-200.00"))
        self.assertEqual(shift.expected_cash(), Decimal("-200.00"))
        self.assertTrue(
            ActivityLog.objects.filter(action="void", entity_type="Invoice").exists()
        )
        # The voided sale is out of revenue and the void note is not
        # subtracted a second time.
        summary = operating_summary(self.company.pk)
        self.assertEqual(Decimal(summary["revenue"]), Decimal("0"))

    def test_paid_invoice_cannot_be_voided_without_a_refund(self):
        invoice = Invoice.objects.get(pk=self._sell(paid="200.00").data["id"])
        self._as(self.owner)
        response = self.client.post(
            reverse("invoice-void", args=[invoice.pk]), {"reason": "oops"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("refund", response.data)
        invoice.refresh_from_db()
        self.assertFalse(invoice.is_void)

    def test_unpaid_invoice_voids_without_refund_and_clears_the_debt(self):
        invoice = Invoice.objects.get(pk=self._sell().data["id"])
        self.assertEqual(self.customer.ar_balance(), Decimal("200.00"))
        self._as(self.owner)
        response = self.client.post(
            reverse("invoice-void", args=[invoice.pk]), {"reason": "duplicate"}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.customer.ar_balance(), Decimal("0"))
        self.assertFalse(Refund.objects.exists())

    def test_void_needs_a_manager_and_a_reason(self):
        invoice = Invoice.objects.get(pk=self._sell().data["id"])
        self._as(self.cashier)
        self.assertEqual(
            self.client.post(
                reverse("invoice-void", args=[invoice.pk]), {"reason": "x"}, format="json"
            ).status_code,
            403,
        )
        self._as(self.owner)
        self.assertEqual(
            self.client.post(reverse("invoice-void", args=[invoice.pk]), {}, format="json")
            .status_code,
            400,
        )

    def test_void_is_refused_once_a_return_exists(self):
        invoice = Invoice.objects.get(pk=self._sell().data["id"])
        line = invoice.lines.get()
        self._as(self.owner)
        returned = self.client.post(
            reverse("salesreturn-list"),
            {"invoice": invoice.pk, "lines": [
                {"invoice_line": line.pk, "product": self.product.pk, "quantity": "1"}
            ]},
            format="json",
        )
        self.assertEqual(returned.status_code, 201, returned.data)
        response = self.client.post(
            reverse("invoice-void", args=[invoice.pk]), {"reason": "x"}, format="json"
        )
        self.assertEqual(response.status_code, 400)


class RefundTests(CorrectionBase):
    def _returned_paid_sale(self):
        invoice = Invoice.objects.get(pk=self._sell(paid="200.00").data["id"])
        line = invoice.lines.get()
        self._as(self.owner)
        response = self.client.post(
            reverse("salesreturn-list"),
            {"invoice": invoice.pk, "lines": [
                {"invoice_line": line.pk, "product": self.product.pk, "quantity": "2"}
            ]},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        return invoice, CreditNote.objects.get(invoice=invoice)

    def test_return_on_a_paid_invoice_leaves_credit_until_refunded(self):
        invoice, note = self._returned_paid_sale()
        self.assertEqual(invoice.amount_due(), Decimal("-200.00"))
        summary = self.client.get(reverse("debt-summary"))
        self.assertEqual(summary.data["credit_balance"], "200.00")

        shift = self._open_shift(self.owner)
        response = self.client.post(
            reverse("refund-list"),
            {"credit_note": note.pk, "method": "cash", "amount": "200.00", "shift": shift.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(invoice.amount_due(), Decimal("0"))
        self.assertEqual(self.client.get(reverse("debt-summary")).data["credit_balance"], "0.00")
        statement = self.client.get(
            reverse("customer-debt-statement", args=[self.customer.pk])
        )
        self.assertIn("refund", {row["type"] for row in statement.data["events"]})

    def test_refunds_cannot_exceed_the_note(self):
        invoice, note = self._returned_paid_sale()
        shift = self._open_shift(self.owner)
        first = self.client.post(
            reverse("refund-list"),
            {"credit_note": note.pk, "method": "cash", "amount": "150.00", "shift": shift.pk},
            format="json",
        )
        self.assertEqual(first.status_code, 201, first.data)
        second = self.client.post(
            reverse("refund-list"),
            {"credit_note": note.pk, "method": "cash", "amount": "60.00", "shift": shift.pk},
            format="json",
        )
        self.assertEqual(second.status_code, 400)
        self.assertIn("amount", second.data)

    def test_cash_refund_needs_an_open_drawer_and_bank_refund_needs_an_account(self):
        _, note = self._returned_paid_sale()
        self._as(self.owner)
        cash = self.client.post(
            reverse("refund-list"),
            {"credit_note": note.pk, "method": "cash", "amount": "10.00"},
            format="json",
        )
        self.assertEqual(cash.status_code, 400)
        self.assertIn("shift", cash.data)
        bank = self.client.post(
            reverse("refund-list"),
            {"credit_note": note.pk, "method": "bank_transfer", "amount": "10.00"},
            format="json",
        )
        self.assertEqual(bank.status_code, 400)

    def test_refunded_note_cannot_be_voided_but_a_clean_one_can(self):
        invoice, note = self._returned_paid_sale()
        shift = self._open_shift(self.owner)
        self.client.post(
            reverse("refund-list"),
            {"credit_note": note.pk, "method": "cash", "amount": "50.00", "shift": shift.pk},
            format="json",
        )
        blocked = self.client.post(
            reverse("creditnote-void", args=[note.pk]), {"reason": "x"}, format="json"
        )
        self.assertEqual(blocked.status_code, 400)
        clean = CreditNote.objects.create(
            company=self.company, customer=self.customer, amount=Decimal("5"),
        )
        voided = self.client.post(
            reverse("creditnote-void", args=[clean.pk]), {"reason": "keyed twice"},
            format="json",
        )
        self.assertEqual(voided.status_code, 200, voided.data)
        clean.refresh_from_db()
        self.assertTrue(clean.is_void)
        self.assertIn("VOID", clean.reason)


class CreditNoteCapTests(CorrectionBase):
    def test_standalone_note_cannot_exceed_what_remains_creditable(self):
        invoice = Invoice.objects.get(pk=self._sell().data["id"])
        self._as(self.owner)
        too_much = self.client.post(
            reverse("creditnote-list"),
            {"customer": self.customer.pk, "invoice": invoice.pk, "amount": "250.00",
             "reason": "goodwill"},
            format="json",
        )
        self.assertEqual(too_much.status_code, 400, too_much.data)
        ok = self.client.post(
            reverse("creditnote-list"),
            {"customer": self.customer.pk, "invoice": invoice.pk, "amount": "50.00",
             "reason": "price correction"},
            format="json",
        )
        self.assertEqual(ok.status_code, 201, ok.data)
        # A price correction lowers revenue as well as the debt.
        summary = operating_summary(self.company.pk)
        self.assertEqual(Decimal(summary["revenue"]), Decimal("150.00"))
        self.assertEqual(invoice.amount_due(), Decimal("150.00"))

    def test_price_correction_on_a_taxed_invoice_is_netted_of_tax(self):
        # subtotal 100 / total 115 / note 23 -> the note carries 3 of tax and
        # 20 of revenue. On SQLite a ratio of two whole-number columns used
        # to be computed as integer division (115 / 100 = 1), which left the
        # tax inside the adjustment and understated revenue by 3.
        profile = self.company.tax_profile
        profile.flat_tax_rate = Decimal("15")
        profile.save()
        invoice = Invoice.objects.get(pk=self._sell(qty="1").data["id"])
        self.assertEqual(invoice.subtotal, Decimal("100.00"))
        self.assertEqual(invoice.total, Decimal("115.00"))
        self._as(self.owner)
        ok = self.client.post(
            reverse("creditnote-list"),
            {"customer": self.customer.pk, "invoice": invoice.pk, "amount": "23.00",
             "reason": "price correction"},
            format="json",
        )
        self.assertEqual(ok.status_code, 201, ok.data)
        summary = operating_summary(self.company.pk)
        self.assertEqual(Decimal(summary["revenue"]), Decimal("80.00"))
        self.assertEqual(invoice.amount_due(), Decimal("92.00"))


class PaymentGuardTests(CorrectionBase):
    def test_payment_is_capped_by_the_locked_balance(self):
        invoice = Invoice.objects.get(pk=self._sell().data["id"])
        self._as(self.cashier)
        response = self.client.post(
            reverse("payment-list"),
            {"invoice": invoice.pk, "method": "cash", "amount": "250.00"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("amount", response.data)

    def test_counter_payment_lands_in_the_cashiers_drawer(self):
        invoice = Invoice.objects.get(pk=self._sell().data["id"])
        shift = self._open_shift(self.cashier)
        response = self.client.post(
            reverse("payment-list"),
            {"invoice": invoice.pk, "method": "cash", "amount": "80.00", "shift": shift.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(shift.expected_cash(), Decimal("80.00"))

    def test_only_the_holder_or_a_manager_closes_a_drawer(self):
        shift = self._open_shift(self.cashier)
        other = User.objects.create_user(
            email="till2@alpha.test", password="passw0rd123",
            company=self.company, role=self.sales_role, branch=self.branch,
        )
        self._as(other)
        blocked = self.client.post(
            reverse("cashshift-close", args=[shift.pk]), {"counted_cash": "0"}, format="json"
        )
        self.assertEqual(blocked.status_code, 403)
        self._as(self.owner)
        closed = self.client.post(
            reverse("cashshift-close", args=[shift.pk]), {"counted_cash": "0"}, format="json"
        )
        self.assertEqual(closed.status_code, 200, closed.data)


class CreditControlTests(CorrectionBase):
    def test_sale_on_account_needs_a_named_customer(self):
        response = self._sell(customer=False)
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("customer", response.data)
        paid = self._sell(customer=False, paid="200.00")
        self.assertEqual(paid.status_code, 201, paid.data)

    def test_credit_hold_blocks_new_credit_but_not_cash(self):
        self.customer.credit_hold = True
        self.customer.save(update_fields=["credit_hold"])
        self.assertEqual(self._sell().status_code, 400)
        self.assertEqual(self._sell(paid="200.00").status_code, 201)

    def test_credit_limit_is_enforced_for_staff_and_overridable_by_a_manager(self):
        self.customer.credit_limit = Decimal("250.00")
        self.customer.save(update_fields=["credit_limit"])
        self.assertEqual(self._sell().status_code, 201)  # 200 owed
        blocked = self._sell()  # would be 400 owed
        self.assertEqual(blocked.status_code, 400, blocked.data)
        allowed = self._sell(user=self.owner)
        self.assertEqual(allowed.status_code, 201, allowed.data)
        self.assertTrue(
            ActivityLog.objects.filter(action="credit_limit_override").exists()
        )

    def test_only_a_manager_sets_credit_terms(self):
        self._as(self.cashier)
        response = self.client.patch(
            reverse("customer-detail", args=[self.customer.pk]),
            {"credit_limit": "1000"}, format="json",
        )
        self.assertEqual(response.status_code, 400)
        self._as(self.owner)
        response = self.client.patch(
            reverse("customer-detail", args=[self.customer.pk]),
            {"credit_limit": "1000"}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)


class PayablesTests(CorrectionBase):
    def setUp(self):
        super().setUp()
        self.supplier = Supplier.objects.create(company=self.company, name="Importer")
        self.bill = Bill.objects.create(
            company=self.company, supplier=self.supplier,
            subtotal=Decimal("1000"), total=Decimal("1000"),
        )

    def test_debit_note_on_a_bill_reduces_that_bill_and_ap_once(self):
        DebitNote.objects.create(
            company=self.company, supplier=self.supplier, bill=self.bill, amount=Decimal("300"),
        )
        self.assertEqual(self.bill.amount_due(), Decimal("700"))
        self.assertEqual(self.supplier.ap_balance(), Decimal("700"))
        DebitNote.objects.create(
            company=self.company, supplier=self.supplier, amount=Decimal("100"),
        )
        self.assertEqual(self.supplier.ap_balance(), Decimal("600"))
        self._as(self.owner)
        aging = self.client.get(reverse("report-ap-aging"))
        self.assertEqual(aging.status_code, 200, aging.data)
        self.assertEqual(Decimal(aging.data[0]["total"]), Decimal("700"))

    def test_bill_void_removes_it_from_ap_unless_paid(self):
        self._as(self.owner)
        response = self.client.post(
            reverse("bill-void", args=[self.bill.pk]), {"reason": "keyed 1000 for 100"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.supplier.ap_balance(), Decimal("0"))
        paid_bill = Bill.objects.create(
            company=self.company, supplier=self.supplier, subtotal=Decimal("50"),
            total=Decimal("50"),
        )
        from purchasing.models import SupplierPayment

        SupplierPayment.objects.create(
            company=self.company, supplier=self.supplier, bill=paid_bill,
            method="cash", amount=Decimal("50"),
        )
        blocked = self.client.post(
            reverse("bill-void", args=[paid_bill.pk]), {"reason": "x"}, format="json"
        )
        self.assertEqual(blocked.status_code, 400)

    def test_purchase_return_debit_note_is_capped_at_cost_for_staff(self):
        from purchasing.models import GoodsReceipt, GoodsReceiptLine

        receipt = GoodsReceipt.objects.create(
            company=self.company, supplier=self.supplier, warehouse=self.wh,
        )
        movement = StockMovement.objects.create(
            company=self.company, product=self.product, warehouse=self.wh,
            movement_type=StockMovement.PURCHASE_IN, quantity=Decimal("5"),
            unit_cost=Decimal("60"), reference_type="GoodsReceipt",
            reference_id=str(receipt.pk),
        )
        line = GoodsReceiptLine.objects.create(
            receipt=receipt, product=self.product, quantity=Decimal("5"),
            unit_cost=Decimal("60"), movement=movement,
        )
        buyer_role = Role.objects.create(
            name="Purchasing Officer", scope_level=Role.SCOPE_BUSINESS
        )
        buyer = User.objects.create_user(
            email="buyer@alpha.test", password="passw0rd123",
            company=self.company, role=buyer_role,
        )
        body = {
            "supplier": self.supplier.pk, "warehouse": self.wh.pk,
            "goods_receipt": receipt.pk, "debit_amount": "999.00",
            "lines": [{"goods_receipt_line": line.pk, "quantity": "1"}],
        }
        self._as(buyer)
        blocked = self.client.post(reverse("purchasereturn-list"), body, format="json")
        self.assertEqual(blocked.status_code, 400, blocked.data)
        self._as(self.owner)
        allowed = self.client.post(reverse("purchasereturn-list"), body, format="json")
        self.assertEqual(allowed.status_code, 201, allowed.data)
        self.assertEqual(DebitNote.objects.get().amount, Decimal("999.00"))


class ReturnRevenueBasisTests(CorrectionBase):
    def test_returned_units_reverse_the_discounted_price_not_list_price(self):
        self._as(self.cashier)
        sale = self.client.post(
            reverse("pos-checkout"),
            {
                "warehouse": self.wh.id, "customer": self.customer.id,
                "lines": [{"product": self.product.id, "quantity": "2",
                           "discount_percent": "50"}],
                "payment": {"method": "cash", "amount": "100.00"},
            },
            format="json",
        )
        self.assertEqual(sale.status_code, 201, sale.data)
        invoice = Invoice.objects.get(pk=sale.data["id"])
        line = invoice.lines.get()
        self._as(self.owner)
        self.client.post(
            reverse("salesreturn-list"),
            {"invoice": invoice.pk, "lines": [
                {"invoice_line": line.pk, "product": self.product.pk, "quantity": "1"}
            ]},
            format="json",
        )
        summary = operating_summary(self.company.pk)
        self.assertEqual(Decimal(summary["gross_sales"]), Decimal("100.00"))
        self.assertEqual(Decimal(summary["sales_returns"]), Decimal("50.00"))
        self.assertEqual(Decimal(summary["revenue"]), Decimal("50.00"))
        self.assertEqual(Payment.objects.count(), 1)

    def test_partial_return_of_a_whole_number_line_divides_exactly(self):
        # 3 units for 100.00 then 1 unit back: 33.33 reversed, 66.67 kept.
        # SQLite stores whole decimals as integers and would otherwise divide
        # 1 * 100 / 3 as integers (33), which PostgreSQL never does.
        sale = self._sell(qty="3", paid="300.00")
        self.assertEqual(sale.status_code, 201, sale.data)
        invoice = Invoice.objects.get(pk=sale.data["id"])
        line = invoice.lines.get()
        # Reprice the stored line so 3 units net to exactly 100.00; the
        # checkout's per-unit price can't express 100/3 in two decimals.
        line.line_subtotal = line.line_total = Decimal("100.00")
        line.save(update_fields=["line_subtotal", "line_total"])
        Invoice.objects.filter(pk=invoice.pk).update(
            subtotal=Decimal("100.00"), total=Decimal("100.00")
        )
        self._as(self.owner)
        response = self.client.post(
            reverse("salesreturn-list"),
            {"invoice": invoice.pk, "lines": [
                {"invoice_line": line.pk, "product": self.product.pk, "quantity": "1"}
            ]},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        summary = operating_summary(self.company.pk)
        self.assertEqual(Decimal(summary["gross_sales"]), Decimal("100.00"))
        self.assertEqual(Decimal(summary["sales_returns"]), Decimal("33.33"))
        self.assertEqual(Decimal(summary["revenue"]), Decimal("66.67"))
