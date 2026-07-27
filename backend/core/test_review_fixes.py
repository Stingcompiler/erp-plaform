"""
Regression tests for the CRM / returns / catalogue review.

The headline case is `RestockWarehouseScopeTests`: the disposition endpoint took
its destination warehouse straight from the request body with no validation, so
a user could post returned stock into another company's warehouse.
"""

from datetime import date
from decimal import Decimal

from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import Role, User
from crm.models import Lead
from inventory.models import Product, StockMovement, Warehouse
from org.models import Branch, Company
from returns.models import SalesReturn, SalesReturnLine
from sales.models import Customer, Invoice


class RestockWarehouseScopeTests(APITestCase):
    """Restocking is the one path that puts goods back into sellable stock, so
    the destination has to be somewhere the user is actually responsible for."""

    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        self.other = Company.objects.create(name="Beta")

        self.north = Branch.objects.create(company=self.company, name="North")
        self.south = Branch.objects.create(company=self.company, name="South")

        self.wh_north = Warehouse.objects.create(
            company=self.company, name="North store", branch=self.north
        )
        self.wh_south = Warehouse.objects.create(
            company=self.company, name="South store", branch=self.south
        )
        self.wh_shared = Warehouse.objects.create(
            company=self.company, name="Central"
        )
        self.wh_foreign = Warehouse.objects.create(
            company=self.other, name="Beta store"
        )

        # A Sales Officer: the role that legitimately dispositions customer
        # returns. Using a Purchasing Officer here would now fail at the module
        # gate (see test_returns_split), so these assertions would pass without
        # ever reaching the warehouse check they exist to cover.
        self.role = Role.objects.create(
            name="Sales Officer", scope_level=Role.SCOPE_BRANCH
        )
        self.user = User.objects.create_user(
            email="so@alpha.test", password="passw0rd12345",
            company=self.company, role=self.role, branch=self.north,
        )
        self.product = Product.objects.create(
            company=self.company, sku="P1", name="Widget"
        )
        self.customer = Customer.objects.create(company=self.company, name="C")
        self.invoice = Invoice.objects.create(
            company=self.company, customer=self.customer, branch=self.north,
            warehouse=self.wh_north, number=1,
            subtotal=Decimal("100"), total=Decimal("100"),
        )
        self.client.force_authenticate(self.user)

    def _return_line(self):
        sr = SalesReturn.objects.create(
            company=self.company, invoice=self.invoice, customer=self.customer
        )
        return sr, SalesReturnLine.objects.create(
            sales_return=sr, product=self.product, quantity=Decimal("1"),
            disposition=SalesReturnLine.QUARANTINE,
        )

    def _disposition(self, sr, line, warehouse_id):
        return self.client.post(
            reverse("salesreturn-disposition", args=[sr.id]),
            {"decisions": [
                {"line_id": line.id, "action": "restock", "warehouse": warehouse_id}
            ]},
            format="json",
        )

    def test_cannot_restock_into_another_companys_warehouse(self):
        """The tenancy hole: an unchecked id here corrupts two companies' stock
        at once."""
        sr, line = self._return_line()
        resp = self._disposition(sr, line, self.wh_foreign.id)
        self.assertEqual(resp.status_code, 403, resp.data)
        self.assertFalse(
            StockMovement.objects.filter(warehouse=self.wh_foreign).exists()
        )
        line.refresh_from_db()
        self.assertEqual(line.disposition, SalesReturnLine.QUARANTINE)

    def test_branch_user_cannot_restock_into_another_branch(self):
        sr, line = self._return_line()
        resp = self._disposition(sr, line, self.wh_south.id)
        self.assertEqual(resp.status_code, 403, resp.data)

    def test_branch_user_can_restock_into_own_branch(self):
        sr, line = self._return_line()
        resp = self._disposition(sr, line, self.wh_north.id)
        self.assertEqual(resp.status_code, 200, resp.data)
        line.refresh_from_db()
        self.assertEqual(line.disposition, SalesReturnLine.RESTOCKED)

    def test_shared_warehouse_stays_available(self):
        """A warehouse with no branch belongs to everyone."""
        sr, line = self._return_line()
        resp = self._disposition(sr, line, self.wh_shared.id)
        self.assertEqual(resp.status_code, 200, resp.data)

    def test_business_scoped_user_reaches_every_branch(self):
        owner_role = Role.objects.create(
            name="Business Owner", scope_level=Role.SCOPE_BUSINESS
        )
        owner = User.objects.create_user(
            email="own@alpha.test", password="passw0rd12345",
            company=self.company, role=owner_role,
        )
        self.client.force_authenticate(owner)
        sr, line = self._return_line()
        resp = self._disposition(sr, line, self.wh_south.id)
        self.assertEqual(resp.status_code, 200, resp.data)

    def test_options_endpoint_lists_only_reachable_warehouses(self):
        resp = self.client.get(reverse("salesreturn-restock-warehouses"))
        self.assertEqual(resp.status_code, 200)
        names = {w["name"] for w in resp.data}
        self.assertEqual(names, {"North store", "Central"})

    def test_rollback_leaves_nothing_half_applied(self):
        """The action is atomic — a rejected second decision must not leave the
        first one's stock movement behind."""
        sr = SalesReturn.objects.create(
            company=self.company, invoice=self.invoice, customer=self.customer
        )
        good = SalesReturnLine.objects.create(
            sales_return=sr, product=self.product, quantity=Decimal("1"),
            disposition=SalesReturnLine.QUARANTINE,
        )
        bad = SalesReturnLine.objects.create(
            sales_return=sr, product=self.product, quantity=Decimal("1"),
            disposition=SalesReturnLine.QUARANTINE,
        )
        resp = self.client.post(
            reverse("salesreturn-disposition", args=[sr.id]),
            {"decisions": [
                {"line_id": good.id, "action": "restock",
                 "warehouse": self.wh_north.id},
                {"line_id": bad.id, "action": "restock",
                 "warehouse": self.wh_foreign.id},
            ]},
            format="json",
        )
        self.assertEqual(resp.status_code, 403, resp.data)
        self.assertEqual(StockMovement.objects.count(), 0)
        good.refresh_from_db()
        self.assertEqual(good.disposition, SalesReturnLine.QUARANTINE)


class CatalogueOwnershipTests(APITestCase):
    """An inventory officer owns the catalogue and must be able to maintain it
    without a manager standing by."""

    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        self.role = Role.objects.create(
            name="Inventory Officer", scope_level=Role.SCOPE_BRANCH
        )
        self.user = User.objects.create_user(
            email="io@alpha.test", password="passw0rd12345",
            company=self.company, role=self.role,
        )
        self.product = Product.objects.create(
            company=self.company, sku="P1", name="Widget"
        )
        self.client.force_authenticate(self.user)

    def test_can_edit_a_product(self):
        resp = self.client.patch(
            reverse("product-detail", args=[self.product.id]),
            {"name": "Widget Mk2"}, format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)

    def test_can_archive_a_product(self):
        """Archiving is reversible and destroys nothing, so it should not need
        a manager — that restriction is what makes users demand real deletes."""
        resp = self.client.delete(reverse("product-detail", args=[self.product.id]))
        self.assertEqual(resp.status_code, 204, resp.data)
        self.product.refresh_from_db()
        self.assertFalse(self.product.is_active)

    def test_can_unarchive_a_product(self):
        self.product.is_active = False
        self.product.save(update_fields=["is_active"])
        resp = self.client.post(reverse("product-unarchive", args=[self.product.id]))
        self.assertEqual(resp.status_code, 200, resp.data)
        self.product.refresh_from_db()
        self.assertTrue(self.product.is_active)

    def test_archived_products_are_hidden_by_default(self):
        self.client.delete(reverse("product-detail", args=[self.product.id]))
        resp = self.client.get(reverse("product-list"))
        self.assertEqual(len(resp.data["results"]), 0)

    def test_archived_products_remain_reachable(self):
        """If archiving hid a row forever it would just be deletion with extra
        steps — and nobody could undo it."""
        self.client.delete(reverse("product-detail", args=[self.product.id]))
        resp = self.client.get(reverse("product-list"), {"archived": "1"})
        self.assertEqual(len(resp.data["results"]), 1)

    def test_export_returns_csv(self):
        resp = self.client.get(reverse("product-export"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/csv", resp["Content-Type"])
        self.assertIn("Widget", resp.content.decode("utf-8"))

    def test_export_is_company_scoped(self):
        other = Company.objects.create(name="Beta")
        Product.objects.create(company=other, sku="X", name="ForeignThing")
        resp = self.client.get(reverse("product-export"))
        self.assertNotIn("ForeignThing", resp.content.decode("utf-8"))


class InvoiceExportTests(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        self.role = Role.objects.create(
            name="Sales Officer", scope_level=Role.SCOPE_BRANCH
        )
        self.user = User.objects.create_user(
            email="so@alpha.test", password="passw0rd12345",
            company=self.company, role=self.role,
        )
        wh = Warehouse.objects.create(company=self.company, name="W")
        cust = Customer.objects.create(company=self.company, name="Nile Retail")
        Invoice.objects.create(
            company=self.company, customer=cust, warehouse=wh, number=1,
            subtotal=Decimal("100"), total=Decimal("100"),
        )
        self.client.force_authenticate(self.user)

    def test_sales_officer_can_export_invoices(self):
        resp = self.client.get(reverse("invoice-export"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8")
        self.assertIn("INV-000001", body)
        self.assertIn("Nile Retail", body)

    def test_export_carries_a_utf8_bom_for_excel(self):
        """Without it Excel mangles every Arabic customer name."""
        resp = self.client.get(reverse("invoice-export"))
        self.assertTrue(resp.content.startswith(b"\xef\xbb\xbf"))


class CrmTests(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        self.role = Role.objects.create(
            name="CRM Officer", scope_level=Role.SCOPE_BRANCH
        )
        self.user = User.objects.create_user(
            email="crm@alpha.test", password="passw0rd12345",
            company=self.company, role=self.role,
        )
        self.client.force_authenticate(self.user)

    def _lead(self, stage=Lead.STAGE_NEW, name="Acme", value="1000"):
        return Lead.objects.create(
            company=self.company, name=name, stage=stage,
            phone="+2491", email="a@acme.test",
            estimated_value=Decimal(value),
        )

    def test_pipeline_values_are_consistently_formatted(self):
        """An empty stage returning '0' beside '1000.00' reads as a bug."""
        self._lead()
        resp = self.client.get(reverse("lead-pipeline"))
        self.assertEqual(resp.status_code, 200, resp.data)
        for stage in resp.data.values():
            self.assertRegex(stage["value"], r"^\d+\.\d{2}$", stage["value"])
        self.assertEqual(resp.data["new"]["value"], "1000.00")
        self.assertEqual(resp.data["won"]["value"], "0.00")

    def test_pipeline_counts_every_stage(self):
        self._lead(stage=Lead.STAGE_WON)
        resp = self.client.get(reverse("lead-pipeline"))
        self.assertEqual(set(resp.data), {s for s, _ in Lead.STAGE_CHOICES})
        self.assertEqual(resp.data["won"]["count"], 1)

    def test_won_lead_converts_to_a_customer(self):
        lead = self._lead(stage=Lead.STAGE_WON)
        resp = self.client.post(reverse("lead-convert", args=[lead.id]))
        self.assertEqual(resp.status_code, 201, resp.data)
        customer = Customer.objects.get(pk=resp.data["customer"])
        self.assertEqual(customer.company_id, self.company.id)
        self.assertEqual(customer.name, "Acme")
        self.assertEqual(customer.phone, "+2491")

    def test_conversion_is_idempotent(self):
        """People press this twice when a response is slow."""
        lead = self._lead(stage=Lead.STAGE_WON)
        first = self.client.post(reverse("lead-convert", args=[lead.id]))
        second = self.client.post(reverse("lead-convert", args=[lead.id]))
        self.assertEqual(second.status_code, 200, second.data)
        self.assertFalse(second.data["created"])
        self.assertEqual(first.data["customer"], second.data["customer"])
        self.assertEqual(Customer.objects.filter(company=self.company).count(), 1)

    def test_open_lead_cannot_be_converted(self):
        lead = self._lead(stage=Lead.STAGE_QUALIFIED)
        resp = self.client.post(reverse("lead-convert", args=[lead.id]))
        self.assertEqual(resp.status_code, 400, resp.data)
        self.assertEqual(Customer.objects.count(), 0)

    def test_crm_officer_can_delete_own_lead(self):
        lead = self._lead()
        resp = self.client.delete(reverse("lead-detail", args=[lead.id]))
        self.assertEqual(resp.status_code, 204, resp.data)

    def test_leads_stay_company_scoped(self):
        other = Company.objects.create(name="Beta")
        foreign = Lead.objects.create(company=other, name="Foreign")
        resp = self.client.post(reverse("lead-convert", args=[foreign.id]))
        self.assertEqual(resp.status_code, 404)
