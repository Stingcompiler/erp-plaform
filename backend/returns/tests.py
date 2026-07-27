from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Role, User
from inventory.models import Product, StockMovement, Warehouse
from org.models import Company
from purchasing.models import Bill, Supplier
from returns.models import SalesReturn, SalesReturnLine
from sales.models import Invoice, InvoiceLine


class ReturnsBase(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        self.role = Role.objects.create(name="GM", scope_level=Role.SCOPE_BUSINESS)
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
        StockMovement.objects.create(
            company=self.company, product=self.product, warehouse=self.wh,
            movement_type=StockMovement.PURCHASE_IN, quantity=Decimal("10"),
        )
        before = self.product.on_hand()
        resp = self.client.post(
            reverse("purchasereturn-list"),
            {
                "supplier": supplier.id, "warehouse": self.wh.id,
                "lines": [{"product": self.product.id, "quantity": "3"}],
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
