import uuid
from decimal import Decimal

from django.urls import reverse
from rest_framework import status

from accounts.models import Role
from inventory.models import Product
from integration.base import IntegrationBase


class BackupRestoreRoundTripTests(IntegrationBase):
    """A company's data can be backed up and restored into a fresh company."""

    def setUp(self):
        self.source = self.make_company("Source Co")
        self.client = self.owner_client(self.source, "owner@source.test")
        self.warehouse(self.source)
        self.product(self.source, sku="WIDGET-1", cost="6", price="10")
        self.product(self.source, sku="WIDGET-2", cost="3", price="7")

    def test_backup_then_restore_into_empty_company(self):
        # Take a backup of the source company.
        backup = self.client.post(reverse("ops-backups"))
        self.assertEqual(backup.status_code, status.HTTP_201_CREATED, backup.content)
        dump = backup.data["data"]
        source_skus = {p["sku"] for p in dump["master"]["products"]}
        self.assertEqual(source_skus, {"WIDGET-1", "WIDGET-2"})

        # A brand-new, empty company + its owner.
        target = self.make_company("Target Co")
        role = self.make_role("Business Owner", Role.SCOPE_BUSINESS)
        self.make_user(target, role, "owner@target.test")
        target_client = self.client_for("owner@target.test")

        # Restore the dump into the empty company.
        restore = target_client.post(reverse("ops-restore"), {"data": dump}, format="json")
        self.assertEqual(restore.status_code, status.HTTP_200_OK, restore.content)

        # The products now exist under the target company.
        restored = set(
            Product.objects.filter(company=target).values_list("sku", flat=True)
        )
        self.assertEqual(restored, {"WIDGET-1", "WIDGET-2"})

    def test_restore_refuses_to_clobber_a_populated_company(self):
        dump = self.client.post(reverse("ops-backups")).data["data"]
        # Source already has products -> restoring into it must be rejected.
        resp = self.client.post(reverse("ops-restore"), {"data": dump}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class PluggableTaxAcrossSaleTests(IntegrationBase):
    """A real sale renders differently when the company's tax format changes."""

    def setUp(self):
        self.company = self.make_company("Alpha", tax_rate="10")
        self.client = self.owner_client(self.company, "owner@alpha.test")
        self.wh = self.warehouse(self.company)
        self.product_obj = self.product(self.company, cost="6", price="10")
        # Stock, then sell, to get a real invoice.
        from inventory.models import StockMovement
        StockMovement.objects.create(
            company=self.company, product=self.product_obj, warehouse=self.wh,
            movement_type=StockMovement.PURCHASE_IN, quantity=Decimal("10"),
        )
        checkout = self.client.post(
            reverse("pos-checkout"),
            {
                "client_uuid": str(uuid.uuid4()), "warehouse": self.wh.id,
                "lines": [{"product": self.product_obj.id, "quantity": "2"}],
                "payment": {"method": "cash", "amount": "22"},
            },
            format="json",
        )
        assert checkout.status_code == 201, checkout.content
        self.invoice_id = checkout.data["id"]

    def test_switching_invoice_format_changes_document(self):
        # Simple format first.
        simple = self.client.get(reverse("invoice-document", args=[self.invoice_id]))
        self.assertEqual(simple.data["format"], "simple")
        # 10% tax on subtotal 20 = 2.00
        self.assertEqual(Decimal(simple.data["tax"]), Decimal("2.00"))

        # Switch the company to the Gulf VAT scaffold.
        patch = self.client.patch(
            reverse("tax-profile"),
            {"invoice_format": "gulf_vat", "e_invoicing_enabled": True},
            format="json",
        )
        self.assertEqual(patch.status_code, 200, patch.content)

        gulf = self.client.get(reverse("invoice-document", args=[self.invoice_id]))
        self.assertEqual(gulf.data["format"], "gulf_vat")
        self.assertIn("<Invoice", gulf.data["xml"])
        # The invoice row itself is unchanged — only the rendering differs.
