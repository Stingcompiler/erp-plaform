"""Stock and costing integrity: what the ledger accepts and how it is valued.

Every case here is a way the numbers used to go wrong: stock invented by a
transfer from an empty shelf, a moving average ten times the real price
after an oversell, an internal transfer re-pricing FIFO layers, a return
re-entering at today's cost, a raw `sale_out` posted with no invoice behind
it, a lot of one product attached to a movement of another.
"""
from datetime import timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import Role, User
from core.models import ActivityLog
from inventory.costing import compute
from inventory.models import Product, StockAdjustment, StockBatch, StockMovement, Warehouse
from org.models import Branch, Company
from purchasing.models import GoodsReceipt, PurchaseOrder, PurchaseOrderLine, Supplier
from returns.models import SalesReturnLine
from sales.models import Customer, Invoice


class LedgerBase(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        self.branch = Branch.objects.create(company=self.company, name="Main")
        self.other_branch = Branch.objects.create(company=self.company, name="North")
        self.owner_role = Role.objects.create(
            name="Business Owner", scope_level=Role.SCOPE_BUSINESS
        )
        self.stock_role = Role.objects.create(
            name="Inventory Officer", scope_level=Role.SCOPE_BRANCH
        )
        self.owner = User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123",
            company=self.company, role=self.owner_role,
        )
        self.clerk = User.objects.create_user(
            email="stock@alpha.test", password="passw0rd123",
            company=self.company, role=self.stock_role, branch=self.branch,
        )
        self.wh = Warehouse.objects.create(company=self.company, branch=self.branch, name="WH")
        self.wh2 = Warehouse.objects.create(company=self.company, branch=self.branch, name="WH2")
        self.far = Warehouse.objects.create(
            company=self.company, branch=self.other_branch, name="North WH"
        )
        self.product = Product.objects.create(
            company=self.company, sku="SKU1", name="Widget",
            cost_price=Decimal("5"), sale_price=Decimal("10"),
        )
        self.other_product = Product.objects.create(
            company=self.company, sku="SKU2", name="Gadget", cost_price=Decimal("3"),
        )

    def _in(self, qty, cost, when=None, product=None, warehouse=None, batch=None):
        return StockMovement.objects.create(
            company=self.company, product=product or self.product,
            warehouse=warehouse or self.wh, batch=batch,
            movement_type=StockMovement.PURCHASE_IN, quantity=Decimal(str(qty)),
            unit_cost=Decimal(str(cost)), created_at=when or timezone.now(),
        )


class RawMovementEndpointTests(LedgerBase):
    def _post(self, mtype, qty, **extra):
        self.client.force_authenticate(self.clerk)
        return self.client.post(
            reverse("stockmovement-list"),
            {"product": self.product.pk, "warehouse": self.wh.pk,
             "movement_type": mtype, "quantity": str(qty), **extra},
            format="json",
        )

    def test_only_adjustments_may_be_posted_directly(self):
        for mtype, qty in (("purchase_in", 10), ("sale_out", -1),
                           ("purchase_return_out", -1), ("sales_return_in", 1), ("transfer", 1)):
            with self.subTest(mtype=mtype):
                response = self._post(mtype, qty)
                self.assertEqual(response.status_code, 400, response.data)
                self.assertIn("movement_type", response.data)
        self.assertEqual(self._post("adjustment", 3).status_code, 201)

    def test_a_lot_of_another_product_is_refused(self):
        lot = StockBatch.objects.create(
            company=self.company, product=self.other_product, lot_number="L1"
        )
        response = self._post("adjustment", 1, batch=lot.pk)
        self.assertEqual(response.status_code, 400)
        self.assertIn("batch", response.data)


class AdjustmentControlTests(LedgerBase):
    def _adjust(self, user, qty, **extra):
        self.client.force_authenticate(user)
        body = {"product": self.product.pk, "warehouse": self.wh.pk,
                "quantity": str(qty), "reason": "shelf count", "reason_code": "count"}
        body.update(extra)
        return self.client.post(reverse("stockadjustment-list"), body, format="json")

    def test_reason_is_required_and_coded(self):
        response = self._adjust(self.clerk, -1, reason="")
        self.assertEqual(response.status_code, 400)
        self.assertIn("reason", response.data)
        bad_code = self._adjust(self.clerk, -1, reason_code="magic")
        self.assertEqual(bad_code.status_code, 400)
        ok = self._adjust(self.clerk, -1, reason_code="damage")
        self.assertEqual(ok.status_code, 201, ok.data)
        adjustment = StockAdjustment.objects.get()
        self.assertEqual(adjustment.reason_code, "damage")
        self.assertEqual(adjustment.movement.unit_cost, Decimal("5"))

    def test_large_adjustments_need_an_approver(self):
        self.company.stock_adjustment_approval_threshold = Decimal("100")
        self.company.save(update_fields=["stock_adjustment_approval_threshold"])
        blocked = self._adjust(self.clerk, -50)  # 50 × 5 = 250
        self.assertEqual(blocked.status_code, 400, blocked.data)
        small = self._adjust(self.clerk, -10)  # 50
        self.assertEqual(small.status_code, 201, small.data)
        allowed = self._adjust(self.owner, -50)
        self.assertEqual(allowed.status_code, 201, allowed.data)
        self.assertEqual(StockAdjustment.objects.get(pk=allowed.data["id"]).approved_by, self.owner)


class TransferTests(LedgerBase):
    def _transfer(self, qty, source=None, dest=None, user=None):
        self.client.force_authenticate(user or self.clerk)
        return self.client.post(
            reverse("stocktransfer-list"),
            {"product": self.product.pk, "source_warehouse": (source or self.wh).pk,
             "dest_warehouse": (dest or self.wh2).pk, "quantity": str(qty)},
            format="json",
        )

    def test_cannot_transfer_more_than_is_on_hand(self):
        self._in(10, 5)
        response = self._transfer(100)
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("quantity", response.data)
        self.assertEqual(self.product.on_hand(warehouse=self.wh2), Decimal("0"))
        self.assertEqual(self._transfer(4).status_code, 201)
        self.assertEqual(self.product.on_hand(warehouse=self.wh), Decimal("6"))

    def test_transfer_legs_carry_cost_and_do_not_reprice_fifo(self):
        self._in(10, 5)
        self._in(10, 8)
        self.product.cost_price = Decimal("50")  # a wrong standard cost must not leak in
        self.product.save(update_fields=["cost_price"])
        self.assertEqual(self._transfer(15).status_code, 201)
        StockMovement.objects.create(
            company=self.company, product=self.product, warehouse=self.wh2,
            movement_type=StockMovement.SALE_OUT, quantity=Decimal("-12"),
        )
        result = compute(self.product, "fifo")
        # 12 sold from [10@5, 10@8] → 50 + 16 = 66; 8 left @8 → 64.
        self.assertEqual(result["cogs"], Decimal("66"))
        self.assertEqual(result["valuation"], Decimal("64"))
        self.assertEqual(result["on_hand"], Decimal("8"))

    def test_branch_user_may_send_stock_to_another_branch(self):
        self._in(10, 5)
        response = self._transfer(3, dest=self.far)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(self.product.on_hand(warehouse=self.far), Decimal("3"))
        # ...but never take from a warehouse outside their branch.
        self._in(10, 5, warehouse=self.far)
        response = self._transfer(1, source=self.far, dest=self.wh)
        self.assertEqual(response.status_code, 400)


class CostingEngineTests(LedgerBase):
    def test_average_resets_after_an_oversell(self):
        now = timezone.now()
        StockMovement.objects.create(
            company=self.company, product=self.product, warehouse=self.wh,
            movement_type=StockMovement.SALE_OUT, quantity=Decimal("-10"),
            created_at=now - timedelta(hours=2),
        )
        self._in(12, 100, when=now - timedelta(hours=1))
        result = compute(self.product, "average")
        # Old formula: (−10×5 + 12×100) / 2 = 575. Correct: the receipt sets
        # the average, 100, and two units remain.
        self.assertEqual(result["valuation"], Decimal("200"))
        self.assertEqual(result["on_hand"], Decimal("2"))

    def test_fifo_receipt_settles_earlier_oversell_before_layering(self):
        now = timezone.now()
        StockMovement.objects.create(
            company=self.company, product=self.product, warehouse=self.wh,
            movement_type=StockMovement.SALE_OUT, quantity=Decimal("-3"),
            created_at=now - timedelta(hours=2),
        )
        self._in(10, 7, when=now - timedelta(hours=1))
        result = compute(self.product, "fifo")
        self.assertEqual(result["on_hand"], Decimal("7"))
        self.assertEqual(result["valuation"], Decimal("49"))

    def test_sales_return_reverses_cogs_at_the_sale_cost(self):
        now = timezone.now()
        self._in(10, 5, when=now - timedelta(hours=3))
        StockMovement.objects.create(
            company=self.company, product=self.product, warehouse=self.wh,
            movement_type=StockMovement.SALE_OUT, quantity=Decimal("-4"),
            unit_cost=Decimal("5"), created_at=now - timedelta(hours=2),
        )
        self.product.cost_price = Decimal("9")  # price rose after the sale
        self.product.save(update_fields=["cost_price"])
        StockMovement.objects.create(
            company=self.company, product=self.product, warehouse=self.wh,
            movement_type=StockMovement.SALES_RETURN_IN, quantity=Decimal("1"),
            unit_cost=Decimal("5"), created_at=now - timedelta(hours=1),
        )
        for method, expected in (("fifo", Decimal("15")), ("average", Decimal("15"))):
            with self.subTest(method=method):
                self.assertEqual(compute(self.product, method)["cogs"], expected)


class ReturnCostAndLotTests(LedgerBase):
    def test_restock_carries_the_sale_cost_and_lot_and_scrap_records_a_loss(self):
        self.product.track_batches = True
        self.product.save(update_fields=["track_batches"])
        lot = StockBatch.objects.create(company=self.company, product=self.product, lot_number="L9")
        self._in(10, 5, batch=lot)
        customer = Customer.objects.create(company=self.company, name="Ahmed")
        self.client.force_authenticate(self.owner)
        sale = self.client.post(
            reverse("pos-checkout"),
            {"warehouse": self.wh.pk, "customer": customer.pk,
             "lines": [{"product": self.product.pk, "quantity": "2"}],
             "payment": {"method": "cash", "amount": "20.00"}},
            format="json",
        )
        self.assertEqual(sale.status_code, 201, sale.data)
        invoice = Invoice.objects.get(pk=sale.data["id"])
        self.product.cost_price = Decimal("9")
        self.product.save(update_fields=["cost_price"])
        returned = self.client.post(
            reverse("salesreturn-list"),
            {"invoice": invoice.pk, "lines": [
                {"invoice_line": invoice.lines.get().pk, "product": self.product.pk,
                 "quantity": "2"}
            ]},
            format="json",
        )
        self.assertEqual(returned.status_code, 201, returned.data)
        line = SalesReturnLine.objects.get()
        # Split the two units: one back to the shelf, one written off.
        self.client.post(
            reverse("salesreturn-list") + f"{returned.data['id']}/disposition/",
            {"decisions": [{"line_id": line.pk, "action": "restock", "warehouse": self.wh.pk}]},
            format="json",
        )
        line.refresh_from_db()
        self.assertEqual(line.restock_movement.unit_cost, Decimal("5"))
        self.assertEqual(line.restock_movement.batch, lot)
        self.assertEqual(self.product.on_hand(batch=lot), Decimal("10"))


class ScrapValueTests(LedgerBase):
    def test_scrapped_return_records_written_off_value(self):
        customer = Customer.objects.create(company=self.company, name="Ahmed")
        self._in(10, 5)
        self.client.force_authenticate(self.owner)
        sale = self.client.post(
            reverse("pos-checkout"),
            {"warehouse": self.wh.pk, "customer": customer.pk,
             "lines": [{"product": self.product.pk, "quantity": "3"}],
             "payment": {"method": "cash", "amount": "30.00"}},
            format="json",
        )
        invoice = Invoice.objects.get(pk=sale.data["id"])
        returned = self.client.post(
            reverse("salesreturn-list"),
            {"invoice": invoice.pk, "lines": [
                {"invoice_line": invoice.lines.get().pk, "product": self.product.pk,
                 "quantity": "3"}
            ]},
            format="json",
        )
        line = SalesReturnLine.objects.get()
        self.client.post(
            reverse("salesreturn-list") + f"{returned.data['id']}/disposition/",
            {"decisions": [{"line_id": line.pk, "action": "scrap"}]},
            format="json",
        )
        line.refresh_from_db()
        self.assertEqual(line.written_off_value, Decimal("15.00"))


class ReceivingTests(LedgerBase):
    def setUp(self):
        super().setUp()
        self.supplier = Supplier.objects.create(company=self.company, name="Importer")
        self.client.force_authenticate(self.owner)

    def _receive(self, **extra):
        body = {"supplier": self.supplier.pk, "warehouse": self.wh.pk,
                "lines": [{"product": self.product.pk, "quantity": "10", "unit_cost": "2.00"}]}
        body.update(extra)
        return self.client.post(reverse("receiving-create"), body, format="json")

    def test_foreign_currency_receipt_needs_a_rate_and_lands_in_company_currency(self):
        missing = self._receive(currency="USD")
        self.assertEqual(missing.status_code, 400, missing.data)
        self.assertIn("exchange_rate", missing.data)
        ok = self._receive(currency="USD", exchange_rate="600")
        self.assertEqual(ok.status_code, 201, ok.data)
        receipt = GoodsReceipt.objects.get()
        self.assertEqual(receipt.currency, "USD")
        self.assertEqual(receipt.lines.get().unit_cost, Decimal("2.00"))  # USD
        self.assertEqual(receipt.lines.get().movement.unit_cost, Decimal("1200.00"))  # SDG
        self.product.refresh_from_db()
        self.assertEqual(self.product.cost_price, Decimal("1200.00"))
        self.assertTrue(ActivityLog.objects.filter(action="cost_update").exists())

    def test_receipt_keeps_its_business_time(self):
        earlier = timezone.now() - timedelta(days=2)
        response = self._receive(occurred_at=earlier.isoformat())
        self.assertEqual(response.status_code, 201, response.data)
        receipt = GoodsReceipt.objects.get()
        self.assertLess(abs((receipt.received_at - earlier).total_seconds()), 2)
        self.assertLess(abs((receipt.lines.get().movement.created_at - earlier).total_seconds()), 2)

    def test_purchase_order_status_follows_receipts_and_transitions_are_guarded(self):
        po = PurchaseOrder.objects.create(
            company=self.company, supplier=self.supplier, status=PurchaseOrder.CONFIRMED,
        )
        PurchaseOrderLine.objects.create(
            purchase_order=po, product=self.product, quantity_ordered=Decimal("20"),
            unit_cost=Decimal("2"), line_total=Decimal("40"),
        )
        self._receive(purchase_order=po.pk)
        po.refresh_from_db()
        self.assertEqual(po.status, PurchaseOrder.PARTIALLY_RECEIVED)
        self._receive(purchase_order=po.pk)
        po.refresh_from_db()
        self.assertEqual(po.status, PurchaseOrder.RECEIVED)
        over = self._receive(purchase_order=po.pk)
        self.assertEqual(over.status_code, 400)
        back = self.client.post(
            reverse("purchaseorder-set-status", args=[po.pk]), {"status": "draft"}, format="json"
        )
        self.assertEqual(back.status_code, 400)


class TaxHandlerRoutingTests(LedgerBase):
    def test_tax_is_computed_by_the_handler_and_rate_is_bounded(self):
        profile = self.company.tax_profile
        profile.flat_tax_rate = Decimal("10")
        profile.save(update_fields=["flat_tax_rate"])
        customer = Customer.objects.create(company=self.company, name="Ahmed")
        self.client.force_authenticate(self.owner)
        quote = self.client.post(
            reverse("quotation-list"),
            {"customer": customer.pk, "lines": [
                {"product": self.product.pk, "quantity": "2", "unit_price": "10"}
            ]},
            format="json",
        )
        self.assertEqual(quote.status_code, 201, quote.data)
        self.assertEqual(Decimal(quote.data["tax_amount"]), Decimal("2.00"))
        bad = self.client.patch(reverse("tax-profile"), {"flat_tax_rate": "150"}, format="json")
        self.assertEqual(bad.status_code, 400, bad.data)
        bad_country = self.client.patch(reverse("tax-profile"), {"country": "Sudan"}, format="json")
        self.assertEqual(bad_country.status_code, 400)
        ok = self.client.patch(reverse("tax-profile"), {"country": "sd"}, format="json")
        self.assertEqual(ok.status_code, 200, ok.data)
        profile.refresh_from_db()
        self.assertEqual(profile.country, "SD")
