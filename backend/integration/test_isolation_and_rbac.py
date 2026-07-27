import uuid
from decimal import Decimal

from django.urls import reverse
from rest_framework import status

from integration.base import IntegrationBase


class CrossCompanyIsolationTests(IntegrationBase):
    """Company A must never see or touch company B's data, in any module."""

    def setUp(self):
        self.a = self.make_company("Alpha")
        self.b = self.make_company("Beta")
        self.a_client = self.owner_client(self.a, "owner@alpha.test")

        self.a_wh = self.warehouse(self.a)
        self.a_product = self.product(self.a, sku="A-1")

        self.b_wh = self.warehouse(self.b, name="Beta WH")
        self.b_product = self.product(self.b, sku="B-1")
        self.b_supplier = self.supplier(self.b, name="Beta Supplier")

    def test_product_list_is_scoped(self):
        resp = self.a_client.get(reverse("product-list"))
        skus = {p["sku"] for p in resp.data["results"]}
        self.assertIn("A-1", skus)
        self.assertNotIn("B-1", skus)

    def test_cannot_sell_into_another_companys_warehouse(self):
        resp = self.a_client.post(
            reverse("pos-checkout"),
            {
                "client_uuid": str(uuid.uuid4()),
                "warehouse": self.b_wh.id,  # not company A's
                "lines": [{"product": self.a_product.id, "quantity": "1"}],
                "payment": {"method": "cash", "amount": "10"},
            },
            format="json",
        )
        self.assertGreaterEqual(resp.status_code, 400)

    def test_cannot_receive_against_another_companys_supplier(self):
        resp = self.a_client.post(
            reverse("receiving-create"),
            {
                "client_uuid": str(uuid.uuid4()),
                "supplier": self.b_supplier.id,  # company B's supplier
                "warehouse": self.a_wh.id,
                "lines": [{"product": self.a_product.id, "quantity": "1"}],
            },
            format="json",
        )
        self.assertGreaterEqual(resp.status_code, 400)

    def test_reports_and_sync_pull_exclude_other_company(self):
        # Give B some stock directly so it has data to potentially leak.
        from inventory.models import StockMovement
        StockMovement.objects.create(
            company=self.b, product=self.b_product, warehouse=self.b_wh,
            movement_type=StockMovement.PURCHASE_IN, quantity=Decimal("99"),
        )
        val = self.a_client.get(reverse("report-inventory-valuation"))
        product_ids = {i["product"] for i in val.data["items"]}
        self.assertNotIn(self.b_product.id, product_ids)

        pull = self.a_client.get(reverse("sync-pull"))
        pulled_skus = {p["sku"] for p in pull.data["changes"].get("products", [])}
        self.assertNotIn("B-1", pulled_skus)


class RoleWorkflowTests(IntegrationBase):
    """RBAC holds across whole workflows, not just single endpoints."""

    def setUp(self):
        self.company = self.make_company("Alpha")
        self.wh = self.warehouse(self.company)
        self.supplier_obj = self.supplier(self.company)
        self.product_obj = self.product(self.company)

    def _client(self, role_name, scope, email):
        role = self.make_role(role_name, scope)
        self.make_user(self.company, role, email)
        return self.client_for(email)

    def test_sales_officer_can_sell_but_not_receive(self):
        from accounts.models import Role
        c = self._client("Sales Officer", Role.SCOPE_BRANCH, "sales@alpha.test")
        # Give stock to sell (ORM, since this user can't receive).
        from inventory.models import StockMovement
        StockMovement.objects.create(
            company=self.company, product=self.product_obj, warehouse=self.wh,
            movement_type=StockMovement.PURCHASE_IN, quantity=Decimal("10"),
        )
        sell = c.post(
            reverse("pos-checkout"),
            {
                "client_uuid": str(uuid.uuid4()), "warehouse": self.wh.id,
                "lines": [{"product": self.product_obj.id, "quantity": "1"}],
                "payment": {"method": "cash", "amount": "10"},
            },
            format="json",
        )
        self.assertEqual(sell.status_code, status.HTTP_201_CREATED, sell.content)

        receive = c.post(
            reverse("receiving-create"),
            {
                "client_uuid": str(uuid.uuid4()), "supplier": self.supplier_obj.id,
                "warehouse": self.wh.id,
                "lines": [{"product": self.product_obj.id, "quantity": "5"}],
            },
            format="json",
        )
        self.assertEqual(receive.status_code, status.HTTP_403_FORBIDDEN)

    def test_purchasing_officer_can_receive_but_not_sell(self):
        from accounts.models import Role
        c = self._client("Purchasing Officer", Role.SCOPE_BRANCH, "buy@alpha.test")
        receive = c.post(
            reverse("receiving-create"),
            {
                "client_uuid": str(uuid.uuid4()), "supplier": self.supplier_obj.id,
                "warehouse": self.wh.id,
                "lines": [{"product": self.product_obj.id, "quantity": "5"}],
            },
            format="json",
        )
        self.assertEqual(receive.status_code, status.HTTP_201_CREATED, receive.content)

        sell = c.post(
            reverse("pos-checkout"),
            {
                "client_uuid": str(uuid.uuid4()), "warehouse": self.wh.id,
                "lines": [{"product": self.product_obj.id, "quantity": "1"}],
                "payment": {"method": "cash", "amount": "10"},
            },
            format="json",
        )
        self.assertEqual(sell.status_code, status.HTTP_403_FORBIDDEN)
