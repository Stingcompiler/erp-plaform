import uuid
from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Role, User
from inventory.models import Product, StockMovement, Warehouse
from org.models import Company


class InventoryBase(APITestCase):
    def setUp(self):
        self.company_a = Company.objects.create(name="Alpha")
        self.company_b = Company.objects.create(name="Beta")
        self.role = Role.objects.create(
            name="Inventory Officer", scope_level=Role.SCOPE_BRANCH
        )
        self.user_a = User.objects.create_user(
            email="a@alpha.test", password="passw0rd123",
            company=self.company_a, role=self.role,
        )
        self.wh_a1 = Warehouse.objects.create(company=self.company_a, name="A-WH1")
        self.wh_a2 = Warehouse.objects.create(company=self.company_a, name="A-WH2")
        self.product_a = Product.objects.create(
            company=self.company_a, sku="SKU1", name="Widget", reorder_level=Decimal("5"),
        )
        # Cross-company object to attempt leaks against.
        self.product_b = Product.objects.create(
            company=self.company_b, sku="SKU1", name="Other Widget",
        )
        self.wh_b1 = Warehouse.objects.create(company=self.company_b, name="B-WH1")

        resp = self.client.post(
            reverse("auth-login"), {"email": "a@alpha.test", "password": "passw0rd123"}
        )
        assert resp.status_code == 200, resp.content

    def _move(self, mtype, qty, warehouse, client_uuid=None):
        payload = {
            "product": self.product_a.id,
            "warehouse": warehouse.id,
            "movement_type": mtype,
            "quantity": str(qty),
        }
        if client_uuid:
            payload["client_uuid"] = str(client_uuid)
        return self.client.post(reverse("stockmovement-list"), payload)


class StockLedgerTests(InventoryBase):
    def test_on_hand_is_sum_of_movements(self):
        self._move("purchase_in", 10, self.wh_a1)
        self._move("sale_out", -3, self.wh_a1)
        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.on_hand(), Decimal("7"))

    def test_each_movement_is_exactly_one_row(self):
        self.assertEqual(StockMovement.objects.count(), 0)
        self._move("purchase_in", 10, self.wh_a1)
        self.assertEqual(StockMovement.objects.count(), 1)

    def test_product_has_no_stored_quantity_field(self):
        # Acceptance: stock is derived, never stored. Guards against a future
        # regression that re-introduces a drift-prone mutable field.
        field_names = {f.name for f in Product._meta.get_fields()}
        self.assertNotIn("quantity", field_names)
        self.assertNotIn("quantity_on_hand", field_names)
        self.assertNotIn("current_stock", field_names)

    def test_sign_validation_rejects_wrong_direction(self):
        # purchase_in must be positive.
        resp = self._move("purchase_in", -5, self.wh_a1)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_stock_endpoint_breaks_down_by_warehouse(self):
        self._move("purchase_in", 10, self.wh_a1)
        self._move("purchase_in", 4, self.wh_a2)
        url = reverse("product-stock", args=[self.product_a.id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Decimal(str(resp.data["on_hand"])), Decimal("14"))
        self.assertEqual(len(resp.data["by_warehouse"]), 2)


class IdempotencyTests(InventoryBase):
    def test_replaying_same_client_uuid_does_not_double_apply(self):
        cu = uuid.uuid4()
        r1 = self._move("purchase_in", 10, self.wh_a1, client_uuid=cu)
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        r2 = self._move("purchase_in", 10, self.wh_a1, client_uuid=cu)
        # Replay is accepted but returns the existing row, not a new one.
        self.assertEqual(r2.status_code, status.HTTP_200_OK)
        self.assertEqual(StockMovement.objects.count(), 1)
        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.on_hand(), Decimal("10"))


class TransferTests(InventoryBase):
    def test_transfer_creates_two_movements_and_conserves_total(self):
        self._move("purchase_in", 10, self.wh_a1)
        resp = self.client.post(
            reverse("stocktransfer-list"),
            {
                "product": self.product_a.id,
                "source_warehouse": self.wh_a1.id,
                "dest_warehouse": self.wh_a2.id,
                "quantity": "4",
            },
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        transfer_moves = StockMovement.objects.filter(movement_type="transfer")
        self.assertEqual(transfer_moves.count(), 2)
        self.product_a.refresh_from_db()
        # Company-wide total unchanged...
        self.assertEqual(self.product_a.on_hand(), Decimal("10"))
        # ...but per-warehouse totals moved.
        self.assertEqual(self.product_a.on_hand(warehouse=self.wh_a1), Decimal("6"))
        self.assertEqual(self.product_a.on_hand(warehouse=self.wh_a2), Decimal("4"))

    def test_transfer_same_warehouse_rejected(self):
        resp = self.client.post(
            reverse("stocktransfer-list"),
            {
                "product": self.product_a.id,
                "source_warehouse": self.wh_a1.id,
                "dest_warehouse": self.wh_a1.id,
                "quantity": "4",
            },
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class AdjustmentTests(InventoryBase):
    def test_adjustment_creates_single_typed_movement(self):
        resp = self.client.post(
            reverse("stockadjustment-list"),
            {
                "product": self.product_a.id,
                "warehouse": self.wh_a1.id,
                "quantity": "-2",
                "reason": "damaged",
            },
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        moves = StockMovement.objects.filter(movement_type="adjustment")
        self.assertEqual(moves.count(), 1)
        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.on_hand(), Decimal("-2"))


class InventoryScopingTests(InventoryBase):
    def test_product_list_scoped_to_company(self):
        resp = self.client.get(reverse("product-list"))
        skus = {(p["id"]) for p in resp.data["results"]}
        self.assertIn(self.product_a.id, skus)
        self.assertNotIn(self.product_b.id, skus)

    def test_cannot_move_stock_for_other_company_product(self):
        resp = self.client.post(
            reverse("stockmovement-list"),
            {
                "product": self.product_b.id,  # belongs to company B
                "warehouse": self.wh_a1.id,
                "movement_type": "purchase_in",
                "quantity": "5",
            },
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_movement_endpoint_is_append_only(self):
        self._move("purchase_in", 10, self.wh_a1)
        mv = StockMovement.objects.first()
        # No update/delete routes exist on the append-only viewset.
        detail = reverse("stockmovement-detail", args=[mv.id])
        self.assertEqual(
            self.client.put(detail, {"quantity": "999"}).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            self.client.delete(detail).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def test_low_stock_lists_products_at_or_below_reorder(self):
        # product_a reorder_level=5; put it at 3 -> should appear.
        self._move("purchase_in", 3, self.wh_a1)
        resp = self.client.get(reverse("product-low-stock"))
        ids = {p["id"] for p in resp.data["results"]}
        self.assertIn(self.product_a.id, ids)


class BarcodeTests(APITestCase):
    """Scanning depends on a barcode resolving to exactly one product."""

    def setUp(self):
        self.company = Company.objects.create(name="BarCo")
        self.other = Company.objects.create(name="OtherCo")
        self.role = Role.objects.create(
            name="Inventory Officer", scope_level=Role.SCOPE_BRANCH
        )
        self.user = User.objects.create_user(
            email="bc@barco.test", password="passw0rd12345",
            company=self.company, role=self.role,
        )
        self.client.force_authenticate(self.user)
        self.product = Product.objects.create(
            company=self.company, sku="P1", name="Scanned Item",
            barcode="6291041500213", sale_price=Decimal("10"),
        )

    def test_lookup_by_barcode_exact_match(self):
        resp = self.client.get(
            reverse("product-by-barcode"), {"code": "6291041500213"}
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["id"], self.product.id)

    def test_unknown_barcode_returns_404(self):
        resp = self.client.get(reverse("product-by-barcode"), {"code": "0000000000000"})
        self.assertEqual(resp.status_code, 404)

    def test_missing_code_returns_400(self):
        self.assertEqual(
            self.client.get(reverse("product-by-barcode")).status_code, 400
        )

    def test_barcode_is_not_fuzzy_matched(self):
        # A partial code must NOT resolve — that would sell the wrong item.
        resp = self.client.get(reverse("product-by-barcode"), {"code": "62910"})
        self.assertEqual(resp.status_code, 404)

    def test_other_company_barcode_is_invisible(self):
        Product.objects.create(
            company=self.other, sku="X1", name="Theirs", barcode="1111111111116",
        )
        resp = self.client.get(reverse("product-by-barcode"), {"code": "1111111111116"})
        self.assertEqual(resp.status_code, 404)

    def test_duplicate_barcode_rejected(self):
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            Product.objects.create(
                company=self.company, sku="P2", name="Dup",
                barcode="6291041500213",
            )

    def test_blank_barcodes_may_repeat(self):
        Product.objects.create(company=self.company, sku="P3", name="A", barcode="")
        Product.objects.create(company=self.company, sku="P4", name="B", barcode="")
        self.assertEqual(Product.objects.filter(barcode="").count(), 2)

    def test_generate_internal_barcode(self):
        from inventory.barcodes import is_valid_ean13
        local = Product.objects.create(company=self.company, sku="L1", name="Local")
        resp = self.client.post(reverse("product-generate-barcode", args=[local.id]))
        self.assertEqual(resp.status_code, 200, resp.data)
        code = resp.data["barcode"]
        self.assertTrue(is_valid_ean13(code))
        self.assertTrue(code.startswith("2"))  # GS1 internal-use prefix

    def test_generated_codes_are_unique(self):
        a = Product.objects.create(company=self.company, sku="L2", name="A")
        b = Product.objects.create(company=self.company, sku="L3", name="B")
        ca = self.client.post(reverse("product-generate-barcode", args=[a.id])).data["barcode"]
        cb = self.client.post(reverse("product-generate-barcode", args=[b.id])).data["barcode"]
        self.assertNotEqual(ca, cb)

    def test_generate_refuses_to_overwrite(self):
        resp = self.client.post(
            reverse("product-generate-barcode", args=[self.product.id])
        )
        self.assertEqual(resp.status_code, 400)

    def test_ean13_check_digit_matches_known_barcode(self):
        from inventory.barcodes import ean13_check_digit
        self.assertEqual(ean13_check_digit("629104150021"), "3")
