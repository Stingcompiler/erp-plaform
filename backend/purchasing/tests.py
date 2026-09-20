import uuid
from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Role, User
from inventory.models import Product, StockBatch, StockMovement, Warehouse
from org.models import Branch, Company
from purchasing.models import Bill, GoodsReceipt, Supplier
from sales.models import CompanyBankAccount


class PurchasingBase(APITestCase):
    def setUp(self):
        self.company_a = Company.objects.create(name="Alpha")
        self.company_b = Company.objects.create(name="Beta")
        self.branch_a = Branch.objects.create(company=self.company_a, name="Main")
        self.role = Role.objects.create(
            name="Purchasing Officer", scope_level=Role.SCOPE_BRANCH
        )
        self.user_a = User.objects.create_user(
            email="a@alpha.test", password="passw0rd123",
            company=self.company_a, branch=self.branch_a, role=self.role,
        )
        self.wh_a = Warehouse.objects.create(
            company=self.company_a, branch=self.branch_a, name="A-WH"
        )
        self.product = Product.objects.create(
            company=self.company_a, sku="SKU1", name="Widget",
            cost_price=Decimal("40.00"),
        )
        self.batch_product = Product.objects.create(
            company=self.company_a, sku="SKU2", name="Perishable",
            cost_price=Decimal("10.00"), track_batches=True,
        )
        self.supplier = Supplier.objects.create(company=self.company_a, name="Acme")
        self.bank_a = CompanyBankAccount.objects.create(
            company=self.company_a, bank_name="Bank of Alpha", account_name="Alpha",
        )
        r = self.client.post(
            reverse("auth-login"), {
                "email": "a@alpha.test",
                "password": "passw0rd123",
                "device_id": "TEST",
            }
        )
        assert r.status_code == 200, r.content

    def receive(self, lines, client_uuid=None):
        payload = {"supplier": self.supplier.id, "warehouse": self.wh_a.id, "lines": lines}
        if client_uuid:
            payload["client_uuid"] = str(client_uuid)
        return self.client.post(reverse("receiving-create"), payload, format="json")


class ReceivingTests(PurchasingBase):
    def test_receiving_increases_stock_by_exact_quantity(self):
        resp = self.receive([{"product": self.product.id, "quantity": "10"}])
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        moves = StockMovement.objects.filter(movement_type="purchase_in")
        self.assertEqual(moves.count(), 1)
        self.assertEqual(moves.first().quantity, Decimal("10"))
        self.product.refresh_from_db()
        self.assertEqual(self.product.on_hand(), Decimal("10"))

    def test_receiving_creates_batch_when_tracked(self):
        resp = self.receive([{
            "product": self.batch_product.id, "quantity": "5",
            "lot_number": "LOT-1", "expiry_date": "2027-01-01",
        }])
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        batch = StockBatch.objects.get(lot_number="LOT-1")
        self.assertEqual(batch.product, self.batch_product)
        # on-hand for that batch derives from the movement.
        self.assertEqual(self.batch_product.on_hand(batch=batch), Decimal("5"))

    def test_receiving_is_idempotent(self):
        cu = uuid.uuid4()
        r1 = self.receive([{"product": self.product.id, "quantity": "10"}], client_uuid=cu)
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        r2 = self.receive([{"product": self.product.id, "quantity": "10"}], client_uuid=cu)
        self.assertEqual(r2.status_code, status.HTTP_200_OK)
        self.assertEqual(GoodsReceipt.objects.count(), 1)
        self.assertEqual(
            StockMovement.objects.filter(movement_type="purchase_in").count(), 1
        )

    def test_default_unit_cost_from_product(self):
        self.receive([{"product": self.product.id, "quantity": "3"}])
        mv = StockMovement.objects.filter(movement_type="purchase_in").first()
        self.assertEqual(mv.unit_cost, Decimal("40.00"))

    def test_cannot_receive_other_company_product(self):
        other = Product.objects.create(
            company=self.company_b, sku="X", name="Other",
        )
        resp = self.receive([{"product": other.id, "quantity": "1"}])
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class ReceivingBatchRulesTests(PurchasingBase):
    def test_tracked_product_needs_a_lot(self):
        resp = self.receive([{"product": self.batch_product.id, "quantity": "5"}])
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)
        self.assertIn("SKU2", str(resp.data))
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_past_expiry_is_refused(self):
        resp = self.receive([{
            "product": self.batch_product.id, "quantity": "5",
            "lot_number": "OLD", "expiry_date": "2020-01-01",
        }])
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)
        self.assertEqual(StockBatch.objects.count(), 0)

    def test_untracked_product_needs_nothing_extra(self):
        resp = self.receive([{"product": self.product.id, "quantity": "5"}])
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)


class APBalanceTests(PurchasingBase):
    def test_ap_balance_is_bill_total_minus_payments(self):
        bill = self.client.post(
            reverse("bill-list"),
            {"supplier": self.supplier.id, "total": "500.00"},
            format="json",
        )
        self.assertEqual(bill.status_code, status.HTTP_201_CREATED, bill.content)
        bill_id = bill.data["id"]
        self.client.post(
            reverse("supplierpayment-list"),
            {
                "supplier": self.supplier.id, "bill": bill_id,
                "method": "cash", "amount": "200.00",
            },
            format="json",
        )
        self.supplier.refresh_from_db()
        self.assertEqual(self.supplier.ap_balance(), Decimal("300.00"))

    def test_bill_status_derived_from_payments(self):
        bill = Bill.objects.create(
            company=self.company_a, supplier=self.supplier, total=Decimal("100"),
        )
        self.assertEqual(bill.status, "open")


class SupplierPaymentTests(PurchasingBase):
    def _bill(self):
        return self.client.post(
            reverse("bill-list"),
            {"supplier": self.supplier.id, "total": "100.00"},
            format="json",
        ).data["id"]

    def test_bank_transfer_requires_from_account_and_ref(self):
        bill_id = self._bill()
        resp = self.client.post(
            reverse("supplierpayment-list"),
            {
                "supplier": self.supplier.id, "bill": bill_id,
                "method": "bank_transfer", "amount": "100.00",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_bank_transfer_records_details_no_external_calls(self):
        bill_id = self._bill()
        resp = self.client.post(
            reverse("supplierpayment-list"),
            {
                "supplier": self.supplier.id, "bill": bill_id,
                "method": "bank_transfer", "from_bank_account": self.bank_a.id,
                "reference_last4": "9876", "amount": "100.00",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        self.assertEqual(resp.data["reference_last4"], "9876")

    def test_supplier_payments_append_only(self):
        bill_id = self._bill()
        pay = self.client.post(
            reverse("supplierpayment-list"),
            {"supplier": self.supplier.id, "bill": bill_id, "method": "cash", "amount": "10"},
            format="json",
        ).data
        detail = reverse("supplierpayment-detail", args=[pay["id"]])
        self.assertEqual(self.client.put(detail, {}).status_code, 405)
        self.assertEqual(self.client.delete(detail).status_code, 405)


class PurchasingScopingTests(PurchasingBase):
    def test_supplier_list_scoped(self):
        Supplier.objects.create(company=self.company_b, name="Beta Supplier")
        resp = self.client.get(reverse("supplier-list"))
        names = {s["name"] for s in resp.data["results"]}
        self.assertIn("Acme", names)
        self.assertNotIn("Beta Supplier", names)
