from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Role, User
from inventory.models import Product, StockMovement, Warehouse
from org.models import Company
from purchasing.models import Bill, GoodsReceipt, GoodsReceiptLine, Supplier
from returns.models import CreditNote, SalesReturn, SalesReturnLine
from sales.models import Invoice, InvoiceLine


class ReturnsBase(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        self.role = Role.objects.create(
            name="General Manager", scope_level=Role.SCOPE_BUSINESS
        )
        self.user = User.objects.create_user(
            email="a@alpha.test", password="passw0rd123",
            company=self.company, role=self.role,
        )
        self.wh = Warehouse.objects.create(company=self.company, name="Main")
        self.product = Product.objects.create(
            company=self.company, sku="SKU1", name="Widget",
            sale_price=Decimal("100.00"),
        )
        self.customer = None
        # Build an invoice with stock already sold out.
        self.invoice = Invoice.objects.create(
            company=self.company, warehouse=self.wh, number=1,
            subtotal=Decimal("200"), total=Decimal("200"),
        )
        self.inv_line = InvoiceLine.objects.create(
            invoice=self.invoice, product=self.product, quantity=Decimal("2"),
            unit_price=Decimal("100"), line_subtotal=Decimal("200"),
            line_total=Decimal("200"),
        )
        # Simulate the original sale_out so on_hand starts at -2.
        StockMovement.objects.create(
            company=self.company, product=self.product, warehouse=self.wh,
            movement_type=StockMovement.SALE_OUT, quantity=Decimal("-2"),
        )
        r = self.client.post(
            reverse("auth-login"), {"email": "a@alpha.test", "password": "passw0rd123"}
        )
        assert r.status_code == 200, r.content

    def create_return(self, qty="2"):
        return self.client.post(
            reverse("salesreturn-list"),
            {
                "invoice": self.invoice.id,
                "lines": [{
                    "invoice_line": self.inv_line.id,
                    "product": self.product.id, "quantity": qty,
                }],
            },
            format="json",
        )


class Rule5QuarantineTests(ReturnsBase):
    def test_creating_return_does_not_touch_sellable_stock(self):
        before = self.product.on_hand()
        resp = self.create_return()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        # Rule #5: no sales_return_in movement yet; sellable on-hand unchanged.
        self.assertEqual(
            StockMovement.objects.filter(movement_type="sales_return_in").count(), 0
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.on_hand(), before)
        # Line sits in quarantine.
        line = SalesReturnLine.objects.get()
        self.assertEqual(line.disposition, "quarantine")

    def test_restock_disposition_posts_movement_and_increases_stock(self):
        self.create_return()
        ret = SalesReturn.objects.get()
        line = ret.lines.get()
        before = self.product.on_hand()
        resp = self.client.post(
            reverse("salesreturn-disposition", args=[ret.id]),
            {"decisions": [{"line_id": line.id, "action": "restock"}]},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        line.refresh_from_db()
        self.assertEqual(line.disposition, "restocked")
        self.assertIsNotNone(line.restock_movement)
        self.assertEqual(
            StockMovement.objects.filter(movement_type="sales_return_in").count(), 1
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.on_hand(), before + Decimal("2"))

    def test_scrap_disposition_adds_no_stock(self):
        self.create_return()
        ret = SalesReturn.objects.get()
        line = ret.lines.get()
        before = self.product.on_hand()
        resp = self.client.post(
            reverse("salesreturn-disposition", args=[ret.id]),
            {"decisions": [{"line_id": line.id, "action": "scrap"}]},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        line.refresh_from_db()
        self.assertEqual(line.disposition, "scrapped")
        self.assertEqual(
            StockMovement.objects.filter(movement_type="sales_return_in").count(), 0
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.on_hand(), before)

    def test_cannot_disposition_twice(self):
        self.create_return()
        ret = SalesReturn.objects.get()
        line = ret.lines.get()
        url = reverse("salesreturn-disposition", args=[ret.id])
        self.client.post(
            url,
            {"decisions": [{"line_id": line.id, "action": "scrap"}]},
            format="json",
        )
        resp = self.client.post(
            url, {"decisions": [{"line_id": line.id, "action": "restock"}]}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class CreditNoteARTests(ReturnsBase):
    def test_credit_note_reduces_invoice_amount_due(self):
        # Attach a customer so the credit note can reference one.
        from sales.models import Customer
        cust = Customer.objects.create(company=self.company, name="C1")
        self.invoice.customer = cust
        self.invoice.save(update_fields=["customer"])
        self.assertEqual(self.invoice.amount_due(), Decimal("200"))
        resp = self.client.post(
            reverse("creditnote-list"),
            {"customer": cust.id, "invoice": self.invoice.id, "amount": "50.00"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.amount_due(), Decimal("150"))


class PurchaseReturnTests(ReturnsBase):
    def test_purchase_return_posts_negative_movement(self):
        supplier = Supplier.objects.create(company=self.company, name="Acme")
        # Put some stock in first.
        receipt = GoodsReceipt.objects.create(
            company=self.company, supplier=supplier, warehouse=self.wh
        )
        incoming = StockMovement.objects.create(
            company=self.company, product=self.product, warehouse=self.wh,
            movement_type=StockMovement.PURCHASE_IN, quantity=Decimal("10"),
        )
        receipt_line = GoodsReceiptLine.objects.create(
            receipt=receipt, product=self.product, quantity=Decimal("10"),
            unit_cost=Decimal("1"), movement=incoming,
        )
        before = self.product.on_hand()
        resp = self.client.post(
            reverse("purchasereturn-list"),
            {
                "supplier": supplier.id, "warehouse": self.wh.id,
                "goods_receipt": receipt.id,
                "lines": [{
                    "goods_receipt_line": receipt_line.id, "quantity": "3"
                }],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        self.assertEqual(
            StockMovement.objects.filter(movement_type="purchase_return_out").count(), 1
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.on_hand(), before - Decimal("3"))


class DebitNoteAPTests(ReturnsBase):
    def test_debit_note_reduces_ap_balance(self):
        supplier = Supplier.objects.create(company=self.company, name="Acme")
        Bill.objects.create(company=self.company, supplier=supplier, total=Decimal("500"))
        self.assertEqual(supplier.ap_balance(), Decimal("500"))
        resp = self.client.post(
            reverse("debitnote-list"),
            {"supplier": supplier.id, "amount": "120.00"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        self.assertEqual(supplier.ap_balance(), Decimal("380"))


class Rule4ReturnCapTests(ReturnsBase):
    """
    Rule #4: a return line references the original document, and the quantity
    returned can never exceed what that line actually sold. The invoice built
    in ReturnsBase sold 2 units at 100.
    """

    def post_lines(self, lines, invoice=None):
        return self.client.post(
            reverse("salesreturn-list"),
            {"invoice": (invoice or self.invoice).id, "lines": lines},
            format="json",
        )

    def test_returning_exactly_what_was_sold_is_allowed(self):
        resp = self.create_return(qty="2")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)

    def test_returning_more_than_was_sold_is_rejected(self):
        resp = self.create_return(qty="100")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        # The refusal names the line cap; the wording is localised, so
        # assert on the field it lands in rather than on English prose.
        self.assertIn("lines", resp.data)
        # Nothing was written — no return, and above all no credit note.
        self.assertEqual(SalesReturn.objects.count(), 0)
        self.assertEqual(CreditNote.objects.count(), 0)

    def test_cumulative_returns_cannot_exceed_the_line(self):
        self.assertEqual(self.create_return(qty="1").status_code, 201)
        # 1 more is fine; the 2nd unit is still returnable.
        self.assertEqual(self.create_return(qty="1").status_code, 201)
        # A third crosses the line even though each request looked harmless.
        resp = self.create_return(qty="1")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(SalesReturn.objects.count(), 2)

    def test_duplicate_lines_in_one_payload_are_summed(self):
        # Two lines of 2 against a line that sold 2: each looks valid alone.
        line = {
            "invoice_line": self.inv_line.id,
            "product": self.product.id, "quantity": "2",
        }
        resp = self.post_lines([line, dict(line)])
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(SalesReturn.objects.count(), 0)

    def test_invoice_line_is_required(self):
        resp = self.post_lines(
            [{"product": self.product.id, "quantity": "1"}]
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invoice_line_from_another_invoice_is_rejected(self):
        other_invoice = Invoice.objects.create(
            company=self.company, warehouse=self.wh, number=2,
            subtotal=Decimal("900"), total=Decimal("900"),
        )
        other_line = InvoiceLine.objects.create(
            invoice=other_invoice, product=self.product, quantity=Decimal("9"),
            unit_price=Decimal("100"), line_subtotal=Decimal("900"),
            line_total=Decimal("900"),
        )
        # Claim the big line's quantity while returning against the small one.
        resp = self.post_lines([{
            "invoice_line": other_line.id,
            "product": self.product.id, "quantity": "9",
        }])
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(SalesReturn.objects.count(), 0)

    def test_another_companys_invoice_line_is_rejected(self):
        """Rule #1: InvoiceLine has no company_id, so the tie to the (scoped)
        invoice is the only thing standing between tenants here."""
        other_co = Company.objects.create(name="Beta")
        other_wh = Warehouse.objects.create(company=other_co, name="Beta Main")
        beta_product = Product.objects.create(
            company=other_co, sku="B1", name="Beta Widget",
            sale_price=Decimal("5000.00"),
        )
        beta_invoice = Invoice.objects.create(
            company=other_co, warehouse=other_wh, number=1,
            subtotal=Decimal("50000"), total=Decimal("50000"),
        )
        beta_line = InvoiceLine.objects.create(
            invoice=beta_invoice, product=beta_product, quantity=Decimal("10"),
            unit_price=Decimal("5000"), line_subtotal=Decimal("50000"),
            line_total=Decimal("50000"),
        )
        resp = self.post_lines([{
            "invoice_line": beta_line.id,
            "product": self.product.id, "quantity": "10",
        }])
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(SalesReturn.objects.count(), 0)
        self.assertEqual(CreditNote.objects.count(), 0)

    def test_product_must_match_the_invoice_line(self):
        other_product = Product.objects.create(
            company=self.company, sku="SKU2", name="Gadget",
            sale_price=Decimal("100.00"),
        )
        resp = self.post_lines([{
            "invoice_line": self.inv_line.id,
            "product": other_product.id, "quantity": "1",
        }])
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_returnable_quantity_tracks_prior_returns(self):
        self.assertEqual(self.inv_line.returnable_quantity(), Decimal("2"))
        self.create_return(qty="1")
        self.inv_line.refresh_from_db()
        self.assertEqual(self.inv_line.returned_quantity(), Decimal("1"))
        self.assertEqual(self.inv_line.returnable_quantity(), Decimal("1"))
