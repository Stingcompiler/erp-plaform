"""Inventory review 2026-09-24: lots on adjustments/transfers, archived and
non-stock products, reprice rounding and packs, pack barcodes, branch-scoped
stock figures, low/negative lists and switching lot tracking off."""
import uuid
from decimal import Decimal

from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import Role, User
from core.models import ActivityLog
from inventory.barcodes import build_ean13, next_internal_barcode
from inventory.models import (
    Product,
    ProductPack,
    StockAdjustment,
    StockBatch,
    StockMovement,
    StockTransfer,
    Warehouse,
)
from inventory.pricing import round_to_step
from org.models import Branch, Company


class ReviewBase(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        self.branch = Branch.objects.create(company=self.company, name="Main")
        self.north = Branch.objects.create(company=self.company, name="North")
        self.owner = User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123", company=self.company,
            role=Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS),
        )
        self.clerk = User.objects.create_user(
            email="clerk@alpha.test", password="passw0rd123", company=self.company,
            branch=self.branch,
            role=Role.objects.create(name="Inventory Officer", scope_level=Role.SCOPE_BRANCH),
        )
        self.wh = Warehouse.objects.create(company=self.company, branch=self.branch, name="WH")
        self.wh2 = Warehouse.objects.create(company=self.company, branch=self.branch, name="WH2")
        self.far = Warehouse.objects.create(
            company=self.company, branch=self.north, name="North WH"
        )
        self.product = Product.objects.create(
            company=self.company, sku="SKU1", name="Widget", barcode="111",
            cost_price=Decimal("5"), sale_price=Decimal("10"),
        )
        self.drug = Product.objects.create(
            company=self.company, sku="MED", name="Syrup", track_batches=True,
            cost_price=Decimal("2"), sale_price=Decimal("4"),
        )
        self.l1 = StockBatch.objects.create(
            company=self.company, product=self.drug, lot_number="L1"
        )
        self.other_drug = Product.objects.create(
            company=self.company, sku="MED2", name="Drops", track_batches=True,
        )
        self.foreign_lot = StockBatch.objects.create(
            company=self.company, product=self.other_drug, lot_number="X1"
        )
        self.client.force_authenticate(self.owner)

    def _in(self, product, qty, warehouse=None, batch=None):
        return StockMovement.objects.create(
            company=self.company, product=product, warehouse=warehouse or self.wh,
            batch=batch, movement_type=StockMovement.PURCHASE_IN,
            quantity=Decimal(str(qty)), unit_cost=Decimal("1"),
        )

    def _adjust(self, product, qty, batch=None, warehouse=None):
        body = {"product": product.pk, "warehouse": (warehouse or self.wh).pk,
                "quantity": str(qty), "reason": "count", "reason_code": "count"}
        if batch is not None:
            body["batch"] = batch.pk
        return self.client.post(reverse("stockadjustment-list"), body, format="json")

    def _transfer(self, product, qty, batch=None):
        body = {"product": product.pk, "source_warehouse": self.wh.pk,
                "dest_warehouse": self.wh2.pk, "quantity": str(qty)}
        if batch is not None:
            body["batch"] = batch.pk
        return self.client.post(reverse("stocktransfer-list"), body, format="json")

    def _push(self, op_type, payload):
        cu = str(uuid.uuid4())
        response = self.client.post(reverse("sync-push"), {
            "device_id": "dev-1", "batch_uuid": str(uuid.uuid4()),
            "operations": [{"op_type": op_type, "client_uuid": cu,
                            "payload": {**payload, "client_uuid": cu}}],
        }, format="json")
        self.assertIn(response.status_code, (200, 201), response.content)
        return response.data["results"][0]


class LotRequiredTests(ReviewBase):
    def test_adjustment_of_a_lot_tracked_product_needs_a_lot(self):
        response = self._adjust(self.drug, 5)
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("batch", response.data)
        ok = self._adjust(self.drug, 5, batch=self.l1)
        self.assertEqual(ok.status_code, 201, ok.data)
        self.assertEqual(self.drug.on_hand(warehouse=self.wh, batch=self.l1), Decimal("5"))

    def test_lot_must_belong_to_the_product(self):
        response = self._adjust(self.drug, 5, batch=self.foreign_lot)
        self.assertEqual(response.status_code, 400)
        self.assertIn("batch", response.data)

    def test_negative_adjustment_cannot_empty_a_lot_below_zero(self):
        self._in(self.drug, 3, batch=self.l1)
        self._in(self.drug, 3, warehouse=self.wh2, batch=self.l1)
        short = self._adjust(self.drug, -4, batch=self.l1)
        self.assertEqual(short.status_code, 400, short.data)
        self.assertIn("batch", short.data)
        ok = self._adjust(self.drug, -3, batch=self.l1)
        self.assertEqual(ok.status_code, 201, ok.data)

    def test_transfer_of_a_lot_tracked_product_needs_a_lot_with_enough(self):
        self._in(self.drug, 4, batch=self.l1)
        self.assertEqual(self._transfer(self.drug, 2).status_code, 400)
        self.assertEqual(self._transfer(self.drug, 5, batch=self.l1).status_code, 400)
        ok = self._transfer(self.drug, 4, batch=self.l1)
        self.assertEqual(ok.status_code, 201, ok.data)
        self.assertEqual(self.drug.on_hand(warehouse=self.wh2, batch=self.l1), Decimal("4"))

    def test_old_client_replay_without_a_lot_is_accepted_and_audited(self):
        result = self._push("stock_adjustment", {
            "product": self.drug.pk, "warehouse": self.wh.pk, "quantity": "-2",
            "reason": "broken", "reason_code": "damage",
        })
        self.assertEqual(result["status"], "applied", result)
        self.assertEqual(StockAdjustment.objects.filter(product=self.drug).count(), 1)
        self.assertTrue(ActivityLog.objects.filter(
            action="sync_stock_rule_bypassed", metadata__rule="lot_missing"
        ).exists())

    def test_stock_endpoint_reports_lots_per_warehouse(self):
        self._in(self.drug, 3, batch=self.l1)
        self._in(self.drug, 2, warehouse=self.wh2, batch=self.l1)
        data = self.client.get(reverse("product-stock", args=[self.drug.pk])).data
        self.assertEqual(data["by_batch"][0]["on_hand"], Decimal("5"))
        per = {row["warehouse"]: row["on_hand"] for row in data["by_batch_warehouse"]}
        self.assertEqual(per, {self.wh.pk: Decimal("3"), self.wh2.pk: Decimal("2")})


class ArchivedAndNonStockTests(ReviewBase):
    def setUp(self):
        super().setUp()
        self.pack = ProductPack.objects.create(
            company=self.company, product=self.product, name="Carton",
            quantity=Decimal("12"), barcode="222",
        )
        self.product.is_active = False
        self.product.save(update_fields=["is_active"])

    def test_archived_product_and_its_packs_do_not_scan(self):
        url = reverse("product-by-barcode")
        self.assertEqual(self.client.get(url, {"code": "111"}).status_code, 404)
        self.assertEqual(self.client.get(url, {"code": "222"}).status_code, 404)

    def test_archived_product_is_refused_at_the_live_till(self):
        response = self.client.post(reverse("pos-checkout"), {
            "warehouse": self.wh.pk,
            "lines": [{"product": self.product.pk, "quantity": "1"}],
            "payment": {"method": "cash", "amount": "10.00"},
        }, format="json")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("lines", response.data)

    def test_archived_product_sold_offline_is_kept_and_audited(self):
        result = self._push("pos_checkout", {
            "warehouse": self.wh.pk,
            "lines": [{"product": self.product.pk, "quantity": "1"}],
            "payment": {"method": "cash", "amount": "10.00"},
        })
        self.assertEqual(result["status"], "applied", result)
        self.assertTrue(ActivityLog.objects.filter(action="sold_archived_product").exists())

    def test_archived_product_is_not_adjusted_or_transferred_live(self):
        self._in(self.product, 5)
        self.assertEqual(self._adjust(self.product, 1).status_code, 400)
        self.assertEqual(self._transfer(self.product, 1).status_code, 400)
        result = self._push("stock_adjustment", {
            "product": self.product.pk, "warehouse": self.wh.pk, "quantity": "-1",
            "reason": "found broken", "reason_code": "damage",
        })
        self.assertEqual(result["status"], "applied", result)
        self.assertTrue(ActivityLog.objects.filter(metadata__rule="archived").exists())

    def test_non_stock_product_has_no_stock_to_move(self):
        bag = Product.objects.create(
            company=self.company, sku="BAG", name="Bag", is_stock_tracked=False,
        )
        response = self._adjust(bag, 5)
        self.assertEqual(response.status_code, 400)
        self.assertIn("product", response.data)
        self.assertEqual(self._transfer(bag, 1).status_code, 400)
        self.assertFalse(StockTransfer.objects.exists())

    def test_low_and_negative_lists_leave_archived_products_out(self):
        StockMovement.objects.create(
            company=self.company, product=self.product, warehouse=self.wh,
            movement_type=StockMovement.SALE_OUT, quantity=Decimal("-3"),
        )
        low = self.client.get(reverse("product-low-stock")).data
        negative = self.client.get(reverse("product-negative-stock")).data
        rows = lambda data: {p["id"] for p in data.get("results", data)}  # noqa: E731
        self.assertNotIn(self.product.pk, rows(low))
        self.assertNotIn(self.product.pk, rows(negative))


class RepriceTests(ReviewBase):
    def test_a_positive_price_never_rounds_to_zero(self):
        self.assertEqual(round_to_step(Decimal("30"), "100"), Decimal("100.00"))
        self.assertEqual(round_to_step(Decimal("0.004"), "0.01"), Decimal("0.01"))
        self.assertEqual(round_to_step(Decimal("0"), "100"), Decimal("0.00"))

    def test_rate_mode_keeps_a_cheap_item_priced(self):
        sweet = Product.objects.create(
            company=self.company, sku="SWT", name="Sweet",
            reference_price=Decimal("0.02"), sale_price=Decimal("10"),
        )
        response = self.client.post(reverse("product-reprice"), {
            "mode": "rate", "rate": "600", "step": "100",
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        sweet.refresh_from_db()
        self.assertEqual(sweet.sale_price, Decimal("100.00"))

    def test_percent_mode_keeps_a_cheap_item_priced_and_packs_follow(self):
        self.product.sale_price = Decimal("30")
        self.product.save(update_fields=["sale_price"])
        carton = ProductPack.objects.create(
            company=self.company, product=self.product, name="Carton",
            quantity=Decimal("12"), sale_price=Decimal("300"),
        )
        loose = ProductPack.objects.create(
            company=self.company, product=self.product, name="Strip",
            quantity=Decimal("10"),
        )
        response = self.client.post(reverse("product-reprice"), {
            "mode": "percent", "percent": "100", "step": "10",
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["packs_changed"], 1)
        self.product.refresh_from_db()
        carton.refresh_from_db()
        loose.refresh_from_db()
        self.assertEqual(self.product.sale_price, Decimal("60.00"))
        # Scaled by the product's own factor (x2), keeping its discount.
        self.assertEqual(carton.sale_price, Decimal("600.00"))
        self.assertIsNone(loose.sale_price)
        cut = self.client.post(reverse("product-reprice"), {
            "mode": "percent", "percent": "-99", "step": "100",
        }, format="json")
        self.assertEqual(cut.status_code, 200, cut.data)
        self.product.refresh_from_db()
        self.assertEqual(self.product.sale_price, Decimal("100.00"))


class PackTests(ReviewBase):
    def _pack(self, **body):
        payload = {"product": self.product.pk, "name": "Carton", "quantity": "12"}
        payload.update(body)
        return self.client.post(reverse("productpack-list"), payload, format="json")

    def test_pack_barcode_is_stripped_and_checked_against_products_and_packs(self):
        self.assertEqual(self._pack(barcode="111").status_code, 400)  # its own product
        Product.objects.create(company=self.company, sku="P2", name="Other", barcode="333")
        clash = self._pack(barcode="333")
        self.assertEqual(clash.status_code, 400)
        self.assertIn("barcode", clash.data)
        ok = self._pack(barcode="  444 ")
        self.assertEqual(ok.status_code, 201, ok.data)
        self.assertEqual(ok.data["barcode"], "444")
        dup = self._pack(name="Box", barcode="444")
        self.assertEqual(dup.status_code, 400, dup.data)
        self.assertIn("barcode", dup.data)

    def test_archiving_frees_the_barcode_and_same_name_is_a_clear_400(self):
        created = self._pack(barcode="444")
        pack_url = reverse("productpack-detail", args=[created.data["id"]])
        archived = self.client.patch(pack_url, {"is_active": False}, format="json")
        self.assertEqual(archived.status_code, 200, archived.data)
        self.assertEqual(archived.data["barcode"], "")
        again = self._pack(barcode="444")
        self.assertEqual(again.status_code, 400)
        self.assertIn("name", again.data)
        self.assertIn("مؤرشفة", str(again.data["name"]))  # Arabic by default
        box = self._pack(name="Box", barcode="444")
        self.assertEqual(box.status_code, 201, box.data)
        restored = self.client.patch(
            pack_url, {"is_active": True, "sale_price": "100.00"}, format="json"
        )
        self.assertEqual(restored.status_code, 200, restored.data)
        self.assertTrue(restored.data["is_active"])

    def test_generated_barcode_skips_codes_held_by_packs(self):
        ProductPack.objects.create(
            company=self.company, product=self.product, name="Carton",
            quantity=Decimal("12"), barcode=build_ean13(self.company.pk, 1),
        )
        self.assertEqual(next_internal_barcode(self.company.pk), build_ean13(self.company.pk, 2))


class BranchStockTests(ReviewBase):
    def test_branch_user_sees_own_branch_stock_only(self):
        self._in(self.product, 4)
        self._in(self.product, 10, warehouse=self.far)
        self.client.force_authenticate(self.clerk)
        listed = self.client.get(reverse("product-list"), {"search": "SKU1"}).data["results"]
        self.assertEqual(Decimal(str(listed[0]["on_hand"])), Decimal("4"))
        stock = self.client.get(reverse("product-stock", args=[self.product.pk])).data
        self.assertEqual(stock["on_hand"], Decimal("4"))
        self.assertEqual([row["warehouse"] for row in stock["by_warehouse"]], [self.wh.pk])
        self.client.force_authenticate(self.owner)
        stock = self.client.get(reverse("product-stock", args=[self.product.pk])).data
        self.assertEqual(stock["on_hand"], Decimal("14"))

    def test_search_finds_a_pack_barcode_without_doubling_stock(self):
        self._in(self.product, 4)
        for name, code in (("Carton", "C-1"), ("Box", "C-2")):
            ProductPack.objects.create(
                company=self.company, product=self.product, name=name,
                quantity=Decimal("6"), barcode=code,
            )
        rows = self.client.get(reverse("product-list"), {"search": "C-"}).data["results"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(Decimal(str(rows[0]["on_hand"])), Decimal("4"))
        labels = self.client.get(reverse("product-list"), {"has_barcode": "1"}).data["results"]
        self.assertEqual({p["sku"] for p in labels}, {"SKU1"})


class TrackBatchesSwitchTests(ReviewBase):
    def test_cannot_turn_off_lot_tracking_while_a_lot_holds_stock(self):
        self._in(self.drug, 2, batch=self.l1)
        url = reverse("product-detail", args=[self.drug.pk])
        refused = self.client.patch(url, {"track_batches": False}, format="json")
        self.assertEqual(refused.status_code, 400, refused.data)
        self.assertIn("track_batches", refused.data)
        self.assertEqual(self._adjust(self.drug, -2, batch=self.l1).status_code, 201)
        allowed = self.client.patch(url, {"track_batches": False}, format="json")
        self.assertEqual(allowed.status_code, 200, allowed.data)
