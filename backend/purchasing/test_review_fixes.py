"""Purchasing fixes from the 2026-09-24 review: each test is a thing a buyer
hit (or could) in daily work."""

from datetime import timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, User
from inventory.models import Product
from purchasing.models import Bill, PurchaseOrder, PurchaseOrderLine
from returns.models import DebitNote

from purchasing.tests import PurchasingBase


class PurchasingReviewTests(PurchasingBase):
    def setUp(self):
        super().setUp()
        owner_role = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        self.owner = User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123",
            company=self.company_a, role=owner_role,
        )

    def _order(self, status, product=None):
        po = PurchaseOrder.objects.create(
            company=self.company_a, supplier=self.supplier, branch=self.branch_a, status=status,
        )
        PurchaseOrderLine.objects.create(
            purchase_order=po, product=product or self.product, quantity_ordered=5,
            unit_cost=Decimal("40"), line_total=Decimal("200"),
        )
        return po

    def _bill(self, total="100", number=""):
        return Bill.objects.create(
            company=self.company_a, supplier=self.supplier, total=Decimal(total),
            subtotal=Decimal(total), supplier_invoice_number=number,
        )

    def test_order_lines_say_which_products_need_a_lot(self):
        po = self._order(PurchaseOrder.SENT, product=self.batch_product)
        data = self.client.get(reverse("purchaseorder-detail", args=[po.id])).data
        self.assertTrue(data["lines"][0]["product_track_batches"])

    def test_a_draft_order_cannot_be_received(self):
        po = self._order(PurchaseOrder.DRAFT)
        response = self.client.post(reverse("receiving-create"), {
            "supplier": self.supplier.id, "warehouse": self.wh_a.id, "purchase_order": po.id,
            "lines": [{"product": self.product.id, "quantity": "1"}],
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("purchase_order", response.data)

    def test_the_same_supplier_invoice_is_not_recorded_twice(self):
        self._bill(number="INV-77")
        response = self.client.post(reverse("bill-list"), {
            "supplier": self.supplier.id, "supplier_invoice_number": "inv-77 ",
            "subtotal": "50.00", "tax_amount": "0.00", "total": "50.00",
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("supplier_invoice_number", response.data)

    def test_a_payment_without_a_bill_is_refused_not_a_server_error(self):
        response = self.client.post(reverse("supplierpayment-list"), {
            "supplier": self.supplier.id, "method": "cash", "amount": "10.00",
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("bill", response.data)

    def test_a_debit_note_cannot_exceed_what_the_bill_owes(self):
        bill = self._bill("100")
        self.client.force_authenticate(self.owner)
        response = self.client.post(reverse("debitnote-list"), {
            "supplier": self.supplier.id, "bill": bill.id, "amount": "5000.00",
        }, format="json")
        self.assertEqual(response.status_code, 400)
        ok = self.client.post(reverse("debitnote-list"), {
            "supplier": self.supplier.id, "bill": bill.id, "amount": "20.00",
        }, format="json")
        self.assertEqual(ok.status_code, 201, ok.data)

    def test_a_bill_with_a_debit_note_cannot_be_voided(self):
        bill = self._bill("1000")
        DebitNote.objects.create(
            company=self.company_a, supplier=self.supplier, bill=bill, amount=Decimal("200"),
        )
        self.client.force_authenticate(self.owner)
        response = self.client.post(reverse("bill-void", args=[bill.id]), {"reason": "typo"})
        self.assertEqual(response.status_code, 400)
        bill.refresh_from_db()
        self.assertFalse(bill.is_void)

    def test_the_unpaid_filter_lists_bills_still_owing(self):
        owing = self._bill("100")
        paid = self._bill("50")
        DebitNote.objects.create(
            company=self.company_a, supplier=self.supplier, bill=paid, amount=Decimal("50"),
        )
        rows = self.client.get(reverse("bill-list"), {"unpaid": 1}).data["results"]
        self.assertEqual([row["id"] for row in rows], [owing.id])

    def test_a_late_offline_receipt_does_not_wind_the_cost_back(self):
        now = timezone.now()
        self.client.post(reverse("receiving-create"), {
            "supplier": self.supplier.id, "warehouse": self.wh_a.id,
            "lines": [{"product": self.product.id, "quantity": "1", "unit_cost": "60.00"}],
        }, format="json")
        self.assertEqual(Product.objects.get(pk=self.product.pk).cost_price, Decimal("60.00"))
        late = self.client.post(reverse("receiving-create"), {
            "supplier": self.supplier.id, "warehouse": self.wh_a.id,
            "occurred_at": (now - timedelta(days=3)).isoformat(),
            "lines": [{"product": self.product.id, "quantity": "1", "unit_cost": "30.00"}],
        }, format="json")
        self.assertEqual(late.status_code, 201, late.data)
        self.assertEqual(Product.objects.get(pk=self.product.pk).cost_price, Decimal("60.00"))
