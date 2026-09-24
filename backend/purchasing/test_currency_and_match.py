"""Purchasing follow-ups: foreign-currency documents from the screens, the
receipt picker behind the three-way match, and the order's branch on
receipts."""

from decimal import Decimal

from django.conf import settings
from django.urls import reverse

from accounts.models import Role, User
from inventory.models import Product, StockMovement, Warehouse
from org.models import Branch
from purchasing.models import Bill, GoodsReceipt, PurchaseOrder, PurchaseOrderLine

from purchasing.tests import PurchasingBase


class ForeignCurrencyTests(PurchasingBase):
    def _usd_receipt(self, rate="600", cost="0.10", quantity="10"):
        payload = {
            "supplier": self.supplier.id, "warehouse": self.wh_a.id,
            "currency": "USD",
            "lines": [{"product": self.product.id, "quantity": quantity, "unit_cost": cost}],
        }
        if rate is not None:
            payload["exchange_rate"] = rate
        return self.client.post(reverse("receiving-create"), payload, format="json")

    def test_a_usd_receipt_posts_company_currency_cost(self):
        response = self._usd_receipt()
        self.assertEqual(response.status_code, 201, response.data)
        receipt = GoodsReceipt.objects.get(pk=response.data["id"])
        self.assertEqual(receipt.currency, "USD")
        self.assertEqual(receipt.exchange_rate, Decimal("600"))
        # The line keeps the supplier's price; the ledger and the product
        # cost are in the company currency (0.10 USD x 600 = 60 SDG).
        self.assertEqual(receipt.lines.get().unit_cost, Decimal("0.10"))
        move = StockMovement.objects.get(movement_type=StockMovement.PURCHASE_IN)
        self.assertEqual(move.unit_cost, Decimal("60.00"))
        self.assertEqual(Product.objects.get(pk=self.product.pk).cost_price, Decimal("60.00"))
        self.assertEqual(response.data["received_value"], "1.00")

    def test_a_usd_receipt_needs_its_rate(self):
        response = self._usd_receipt(rate=None)
        self.assertEqual(response.status_code, 400)
        self.assertIn("exchange_rate", response.data)

    def test_a_bill_for_the_receipt_inherits_its_currency_and_rate(self):
        receipt_id = self._usd_receipt().data["id"]
        response = self.client.post(reverse("bill-list"), {
            "supplier": self.supplier.id, "goods_receipt": receipt_id,
            "subtotal": "1.00", "tax_amount": "0.00", "total": "1.00",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        bill = Bill.objects.get(pk=response.data["id"])
        self.assertEqual(bill.currency, "USD")
        self.assertEqual(bill.exchange_rate, Decimal("600"))
        self.assertEqual(self.supplier.ap_balance(), Decimal("600.00"))

    def test_a_bill_cannot_change_the_receipts_currency(self):
        receipt_id = self._usd_receipt().data["id"]
        response = self.client.post(reverse("bill-list"), {
            "supplier": self.supplier.id, "goods_receipt": receipt_id, "currency": "SDG",
            "subtotal": "1.00", "tax_amount": "0.00", "total": "1.00",
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("currency", response.data)

    def test_an_unlinked_bill_defaults_to_the_company_currency(self):
        response = self.client.post(reverse("bill-list"), {
            "supplier": self.supplier.id,
            "subtotal": "50.00", "tax_amount": "0.00", "total": "50.00",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["currency"], "SDG")
        refused = self.client.post(reverse("bill-list"), {
            "supplier": self.supplier.id, "currency": "USD",
            "subtotal": "50.00", "tax_amount": "0.00", "total": "50.00",
        }, format="json")
        self.assertEqual(refused.status_code, 400)
        self.assertIn("exchange_rate", refused.data)

    def _order(self, **extra):
        return self.client.post(reverse("purchaseorder-list"), {
            "supplier": self.supplier.id,
            "lines": [{"product": self.product.id, "quantity_ordered": "5", "unit_cost": "0.10"}],
            **extra,
        }, format="json")

    def test_an_order_is_kept_in_its_currency(self):
        plain = self._order()
        self.assertEqual(plain.status_code, 201, plain.data)
        self.assertEqual(plain.data["currency"], "SDG")
        self.assertEqual(Decimal(plain.data["exchange_rate"]), Decimal("1"))
        self.assertEqual(self._order(currency="USD").status_code, 400)
        self.assertEqual(self._order(currency="SDG", exchange_rate="2").status_code, 400)
        usd = self._order(currency="usd", exchange_rate="600")
        self.assertEqual(usd.status_code, 201, usd.data)
        self.assertEqual(usd.data["currency"], "USD")

    def test_receiving_a_usd_order_takes_the_orders_rate(self):
        order_id = self._order(currency="USD", exchange_rate="600").data["id"]
        PurchaseOrder.objects.filter(pk=order_id).update(status=PurchaseOrder.CONFIRMED)
        response = self.client.post(reverse("receiving-create"), {
            "supplier": self.supplier.id, "warehouse": self.wh_a.id, "purchase_order": order_id,
            "lines": [{"product": self.product.id, "quantity": "5", "unit_cost": "0.10"}],
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["currency"], "USD")
        self.assertEqual(Decimal(response.data["exchange_rate"]), Decimal("600"))
        other = self.client.post(reverse("receiving-create"), {
            "supplier": self.supplier.id, "warehouse": self.wh_a.id, "purchase_order": order_id,
            "currency": "SDG",
            "lines": [{"product": self.product.id, "quantity": "1"}],
        }, format="json")
        self.assertEqual(other.status_code, 400)
        self.assertIn("currency", other.data)

    def test_the_screens_read_the_companys_currencies(self):
        self.company_a.exchange_rate = Decimal("600")
        self.company_a.save(update_fields=["exchange_rate"])
        data = self.client.get(reverse("purchasing-currencies")).data
        self.assertEqual(data["currency"], "SDG")
        self.assertEqual(data["reference_currency"], "USD")
        self.assertEqual(Decimal(data["exchange_rate"]), Decimal("600"))


class ReceiptPickerTests(PurchasingBase):
    def _receipt(self, cost="40.00"):
        response = self.receive([{"product": self.product.id, "quantity": "2", "unit_cost": cost}])
        assert response.status_code == 201, response.data
        return response.data["id"]

    def test_unbilled_lists_receipts_without_a_live_bill(self):
        billed = self._receipt()
        open_one = self._receipt()
        bill = Bill.objects.create(
            company=self.company_a, supplier=self.supplier, goods_receipt_id=billed,
            subtotal=Decimal("80"), total=Decimal("80"),
        )
        url = reverse("goodsreceipt-list")
        rows = self.client.get(url, {"supplier": self.supplier.id, "unbilled": 1}).data["results"]
        self.assertEqual([row["id"] for row in rows], [open_one])
        self.assertEqual(rows[0]["received_value"], "80.00")
        # A voided bill frees its receipt to be billed again.
        Bill.objects.filter(pk=bill.pk).update(is_void=True)
        rows = self.client.get(url, {"supplier": self.supplier.id, "unbilled": 1}).data["results"]
        self.assertEqual(sorted(row["id"] for row in rows), sorted([billed, open_one]))

    def test_the_match_error_reaches_the_screen_in_arabic(self):
        receipt_id = self._receipt()
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "ar"
        response = self.client.post(reverse("bill-list"), {
            "supplier": self.supplier.id, "goods_receipt": receipt_id,
            "subtotal": "500.00", "tax_amount": "0.00", "total": "500.00",
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("subtotal", response.data)
        self.assertIn("لا تطابق الاستلام", str(response.data["subtotal"]))
        self.assertIn("80.00", str(response.data["subtotal"]))


class OrderBranchTests(PurchasingBase):
    def setUp(self):
        super().setUp()
        owner_role = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        self.owner = User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123",
            company=self.company_a, role=owner_role,
        )
        self.client.force_authenticate(self.owner)
        self.branch_b = Branch.objects.create(company=self.company_a, name="North")
        self.wh_b = Warehouse.objects.create(
            company=self.company_a, branch=self.branch_b, name="B-WH"
        )
        self.po = PurchaseOrder.objects.create(
            company=self.company_a, supplier=self.supplier, branch=self.branch_a,
            status=PurchaseOrder.CONFIRMED,
        )
        PurchaseOrderLine.objects.create(
            purchase_order=self.po, product=self.product, quantity_ordered=5,
            unit_cost=Decimal("40"), line_total=Decimal("200"),
        )

    def _receive_into(self, warehouse):
        return self.client.post(reverse("receiving-create"), {
            "supplier": self.supplier.id, "warehouse": warehouse.id,
            "purchase_order": self.po.id,
            "lines": [{"product": self.product.id, "quantity": "1"}],
        }, format="json")

    def test_an_order_is_received_into_its_own_branch(self):
        response = self._receive_into(self.wh_b)
        self.assertEqual(response.status_code, 400)
        self.assertIn("warehouse", response.data)
        self.assertIn("Main", str(response.data["warehouse"]))
        self.assertFalse(GoodsReceipt.objects.exists())
        ok = self._receive_into(self.wh_a)
        self.assertEqual(ok.status_code, 201, ok.data)
