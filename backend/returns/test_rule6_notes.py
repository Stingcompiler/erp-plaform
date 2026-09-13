"""
Rule #6: every return generates a credit/debit note.

Until now the note models existed and could be POSTed by hand, but nothing
generated one — so a return left no document for the other party.

Both sides derive their default value from the original document line: the
invoice line for sales and the goods receipt line for purchasing. Purchasing
may still record an explicitly agreed supplier credit amount.
"""

from decimal import Decimal

from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import Role, User
from inventory.models import Product, StockMovement, Warehouse
from org.models import Branch, Company
from purchasing.models import Bill, GoodsReceipt, GoodsReceiptLine, Supplier
from returns.models import CreditNote, DebitNote, SalesReturn
from sales.models import Customer, Invoice, InvoiceLine


class SalesReturnCreditNoteTests(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        self.branch = Branch.objects.create(company=self.company, name="Main")
        self.role = Role.objects.create(
            name="Sales Officer", scope_level=Role.SCOPE_BRANCH
        )
        self.user = User.objects.create_user(
            email="so@alpha.test", password="passw0rd12345",
            company=self.company, branch=self.branch, role=self.role,
        )
        self.warehouse = Warehouse.objects.create(
            company=self.company, branch=self.branch, name="W"
        )
        self.product = Product.objects.create(
            company=self.company, sku="P1", name="Widget"
        )
        self.customer = Customer.objects.create(company=self.company, name="Nile")
        self.invoice = Invoice.objects.create(
            company=self.company, customer=self.customer, branch=self.branch,
            warehouse=self.warehouse,
            number=1, subtotal=Decimal("500"), total=Decimal("500"),
        )
        self.invoice_line = InvoiceLine.objects.create(
            invoice=self.invoice, product=self.product, description="Widget",
            quantity=Decimal("5"), unit_price=Decimal("100"),
            line_subtotal=Decimal("500"), line_total=Decimal("500"),
        )
        self.client.force_authenticate(self.user)

    def _create(self, quantity="2", with_line=True):
        line = {"product": self.product.id, "quantity": quantity}
        if with_line:
            line["invoice_line"] = self.invoice_line.id
        return self.client.post(
            reverse("salesreturn-list"),
            {"invoice": self.invoice.id, "reason": "Damaged", "lines": [line]},
            format="json",
        )

    def test_return_generates_a_credit_note(self):
        resp = self._create(quantity="2")
        self.assertEqual(resp.status_code, 201, resp.data)
        note = CreditNote.objects.get(company=self.company)
        self.assertEqual(note.amount, Decimal("200.00"))  # 2 x 100
        self.assertEqual(note.customer_id, self.customer.id)
        self.assertEqual(note.invoice_id, self.invoice.id)
        self.assertEqual(note.reason, "Damaged")

    def test_note_is_priced_from_the_invoice_not_the_product(self):
        """The customer is owed what they paid, which may differ from today's
        list price."""
        self.product.sale_price = Decimal("999")
        self.product.save(update_fields=["sale_price"])
        self._create(quantity="1")
        self.assertEqual(
            CreditNote.objects.get(company=self.company).amount, Decimal("100.00")
        )

    def test_note_links_back_to_its_return(self):
        resp = self._create()
        note = CreditNote.objects.get(company=self.company)
        self.assertEqual(note.sales_return_id, resp.data["id"])

    def test_unpriceable_line_is_rejected_outright(self):
        """A line with no invoice_line cannot be valued, and Rule #4 says a
        return is never standalone anyway — so it is refused at the door
        rather than stored as a return that owes the customer nothing.
        (Before the Rule #4 cap landed this was accepted and silently produced
        no note, which is how returns created in the UI went uncredited.)"""
        resp = self._create(with_line=False)
        self.assertEqual(resp.status_code, 400, resp.data)
        self.assertEqual(CreditNote.objects.count(), 0)
        self.assertEqual(SalesReturn.objects.count(), 0)

    def test_walk_in_sale_produces_invoice_linked_credit_note(self):
        """A walk-in return still needs a formal note linked to its invoice."""
        walk_in = Invoice.objects.create(
            company=self.company, customer=None, branch=self.branch,
            warehouse=self.warehouse,
            number=2, subtotal=Decimal("100"), total=Decimal("100"),
        )
        line = InvoiceLine.objects.create(
            invoice=walk_in, product=self.product, description="Widget",
            quantity=Decimal("1"), unit_price=Decimal("100"),
            line_subtotal=Decimal("100"), line_total=Decimal("100"),
        )
        resp = self.client.post(
            reverse("salesreturn-list"),
            {"invoice": walk_in.id, "lines": [
                {"product": self.product.id, "quantity": "1",
                 "invoice_line": line.id}
            ]},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        note = CreditNote.objects.get()
        self.assertIsNone(note.customer_id)
        self.assertEqual(note.invoice_id, walk_in.pk)
        listed = self.client.get(reverse("creditnote-list"))
        self.assertEqual(listed.status_code, 200, listed.data)
        document = self.client.get(reverse("creditnote-document", args=[note.pk]))
        self.assertEqual(document.status_code, 200, document.data)
        self.assertEqual(document.data["party"], {})

    def test_credit_note_reduces_what_the_customer_owes(self):
        self._create(quantity="2")
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.amount_due(), Decimal("300"))


class PurchaseReturnDebitNoteTests(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        self.branch = Branch.objects.create(company=self.company, name="Main")
        self.role = Role.objects.create(
            name="Purchasing Officer", scope_level=Role.SCOPE_BRANCH
        )
        self.user = User.objects.create_user(
            email="po@alpha.test", password="passw0rd12345",
            company=self.company, branch=self.branch, role=self.role,
        )
        self.warehouse = Warehouse.objects.create(
            company=self.company, branch=self.branch, name="W"
        )
        self.product = Product.objects.create(
            company=self.company, sku="P1", name="Widget"
        )
        self.supplier = Supplier.objects.create(company=self.company, name="Delta")
        self.receipt = GoodsReceipt.objects.create(
            company=self.company, supplier=self.supplier, warehouse=self.warehouse
        )
        movement = StockMovement.objects.create(
            company=self.company, product=self.product, warehouse=self.warehouse,
            movement_type=StockMovement.PURCHASE_IN, quantity=Decimal("10"),
            unit_cost=Decimal("50"),
        )
        self.receipt_line = GoodsReceiptLine.objects.create(
            receipt=self.receipt, product=self.product, quantity=Decimal("10"),
            unit_cost=Decimal("50"), movement=movement,
        )
        self.bill = Bill.objects.create(
            company=self.company, supplier=self.supplier,
            goods_receipt=self.receipt, supplier_invoice_number="SUP-1",
            total=Decimal("900"),
        )
        self.client.force_authenticate(self.user)

    def _create(self, **extra):
        body = {
            "supplier": self.supplier.id,
            "warehouse": self.warehouse.id,
            "goods_receipt": self.receipt.id,
            "reason": "Short delivery",
            "lines": [{
                "goods_receipt_line": self.receipt_line.id, "quantity": "3"
            }],
        }
        body.update(extra)
        return self.client.post(
            reverse("purchasereturn-list"), body, format="json"
        )

    def test_return_with_an_amount_generates_a_debit_note(self):
        resp = self._create(debit_amount="150.00", bill=self.bill.id)
        self.assertEqual(resp.status_code, 201, resp.data)
        note = DebitNote.objects.get(company=self.company)
        self.assertEqual(note.amount, Decimal("150.00"))
        self.assertEqual(note.supplier_id, self.supplier.id)
        self.assertEqual(note.bill_id, self.bill.id)
        self.assertEqual(note.purchase_return_id, resp.data["id"])

    def test_return_without_an_amount_uses_received_cost(self):
        resp = self._create()
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(DebitNote.objects.get().amount, Decimal("150"))

    def test_debit_note_reduces_what_we_owe_the_supplier(self):
        before = self.supplier.ap_balance()
        self._create(debit_amount="150.00", bill=self.bill.id)
        self.assertEqual(self.supplier.ap_balance(), before - Decimal("150.00"))

    def test_another_companys_bill_is_rejected(self):
        other = Company.objects.create(name="Beta")
        foreign_supplier = Supplier.objects.create(company=other, name="X")
        foreign_bill = Bill.objects.create(
            company=other, supplier=foreign_supplier, total=Decimal("10")
        )
        resp = self._create(debit_amount="10.00", bill=foreign_bill.id)
        self.assertEqual(resp.status_code, 400, resp.data)
        self.assertEqual(DebitNote.objects.count(), 0)

    def test_stock_leaves_immediately(self):
        """Unlike a sales return there is nothing to quarantine — the goods are
        physically gone."""
        self._create(debit_amount="150.00")
        from inventory.models import StockMovement

        movement = StockMovement.objects.get(
            product=self.product, movement_type=StockMovement.PURCHASE_RETURN_OUT
        )
        self.assertEqual(movement.quantity, Decimal("-3"))
        self.assertEqual(movement.movement_type, StockMovement.PURCHASE_RETURN_OUT)
