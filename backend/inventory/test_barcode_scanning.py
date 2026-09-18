"""What a handheld scanner actually sends versus what the catalogue stores."""

from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import Role, User
from inventory.barcodes import scan_candidates
from inventory.models import Product, ProductPack
from org.models import Branch, Company


class ScanCandidateTests(TestCase):
    def test_upc_a_and_ean13_spellings(self):
        self.assertEqual(scan_candidates("012345678905"), ["012345678905", "0012345678905"])
        self.assertEqual(scan_candidates("0012345678905"), ["0012345678905", "012345678905"])
        self.assertEqual(scan_candidates("6291041500213"), ["6291041500213"])
        self.assertEqual(scan_candidates("ABC-123"), ["ABC-123"])
        self.assertEqual(scan_candidates("  "), [])


class ScanLookupTests(TestCase):
    def setUp(self):
        company = Company.objects.create(name="Alpha")
        branch = Branch.objects.create(company=company, name="Main")
        role = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        user = User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123", company=company, role=role,
            branch=branch,
        )
        self.ean = Product.objects.create(
            company=company, sku="A", name="Widget A", sale_price=Decimal("1"),
            barcode="0012345678905",
        )
        self.other = Product.objects.create(
            company=company, sku="B", name="Widget B", sale_price=Decimal("1"),
            barcode="6291041500213",
        )
        ProductPack.objects.create(
            company=company, product=self.other, name="Carton", quantity=12,
            barcode="16291041500210",
        )
        self.client = APIClient()
        self.client.force_authenticate(user)

    def test_upc_a_scan_finds_the_ean13_product(self):
        response = self.client.get("/api/products/by-barcode/", {"code": "012345678905"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], self.ean.id)

    def test_pack_barcode_still_resolves(self):
        response = self.client.get("/api/products/by-barcode/", {"code": "16291041500210"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], self.other.id)
        self.assertEqual(response.data["scanned_pack"]["quantity"], "12.000")

    def test_duplicate_barcode_is_a_clear_refusal(self):
        response = self.client.post(
            "/api/products/",
            {"name": "Dup", "sku": "DUP", "sale_price": "1", "barcode": "6291041500213"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Widget B", str(response.data["barcode"]))
        pack_clash = self.client.post(
            "/api/products/",
            {"name": "Dup2", "sku": "DUP2", "sale_price": "1", "barcode": "16291041500210"},
            format="json",
        )
        self.assertEqual(pack_clash.status_code, 400)
        # Editing a product keeps its own barcode without tripping the check.
        own = self.client.patch(
            f"/api/products/{self.other.id}/", {"barcode": "6291041500213"}, format="json",
        )
        self.assertEqual(own.status_code, 200)
