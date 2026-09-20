from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Role, User
from inventory.models import Warehouse
from org.models import Branch, Company, TaxProfile
from sales.models import Invoice, InvoiceLine
from tax.handlers import get_handler


class TaxBase(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        self.owner = Role.objects.create(
            name="Business Owner", scope_level=Role.SCOPE_BUSINESS
        )
        self.user = User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123",
            company=self.company, role=self.owner,
        )
        # Company TaxProfile auto-created with flat rate 0; set a rate.
        self.profile = self.company.tax_profile
        self.profile.flat_tax_rate = Decimal("15.00")
        self.profile.save()
        self.wh = Warehouse.objects.create(company=self.company, name="Main")
        self.invoice = Invoice.objects.create(
            company=self.company, warehouse=self.wh, number=1,
            subtotal=Decimal("100"), tax_rate_snapshot=Decimal("15"),
            tax_amount=Decimal("15"), total=Decimal("115"),
        )
        InvoiceLine.objects.create(
            invoice=self.invoice, product=self._product(),
            quantity=Decimal("2"), unit_price=Decimal("50"),
            line_subtotal=Decimal("100"), line_tax=Decimal("15"),
            line_total=Decimal("115"),
        )
        r = self.client.post(
            reverse("auth-login"), {
                "email": "owner@alpha.test",
                "password": "passw0rd123",
                "device_id": "TEST",
            }
        )
        assert r.status_code == 200, r.content

    def _product(self):
        from inventory.models import Product
        return Product.objects.create(
            company=self.company, sku="SKU1", name="Widget",
            sale_price=Decimal("50"),
        )


class HandlerRegistryTests(TaxBase):
    def test_compute_tax_uses_profile_rate(self):
        handler = get_handler(self.profile)
        self.assertEqual(handler.compute_tax(Decimal("100")), Decimal("15.00"))

    def test_handlers_list(self):
        resp = self.client.get(reverse("tax-handlers"))
        codes = {h["code"] for h in resp.data}
        self.assertIn("simple", codes)
        self.assertIn("gulf_vat", codes)


class PluggableRenderingTests(TaxBase):
    def test_simple_format_renders_json(self):
        resp = self.client.get(reverse("invoice-document", args=[self.invoice.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["format"], "simple")
        self.assertEqual(resp.data["content_type"], "application/json")
        self.assertEqual(Decimal(resp.data["tax"]), Decimal("15"))

    def test_switching_format_changes_rendering_no_invoice_change(self):
        # Switch the company to the Gulf VAT scaffold.
        patch = self.client.patch(
            reverse("tax-profile"),
            {"invoice_format": "gulf_vat", "e_invoicing_enabled": True},
            format="json",
        )
        self.assertEqual(patch.status_code, 200, patch.content)
        # Same invoice, different rendering — no change to the Invoice row.
        resp = self.client.get(reverse("invoice-document", args=[self.invoice.id]))
        self.assertEqual(resp.data["format"], "gulf_vat")
        self.assertEqual(resp.data["content_type"], "application/xml")
        self.assertIn("<Invoice", resp.data["xml"])
        self.assertTrue(resp.data["e_invoicing_enabled"])
        # The Invoice model/data is untouched.
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.total, Decimal("115"))

    def test_unknown_format_rejected(self):
        resp = self.client.patch(
            reverse("tax-profile"), {"invoice_format": "klingon"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class TaxRBACAndScopingTests(TaxBase):
    def test_profile_edit_requires_settings_module(self):
        sales = Role.objects.create(name="Sales Officer", scope_level=Role.SCOPE_BRANCH)
        branch = Branch.objects.create(company=self.company, name="Sales branch")
        User.objects.create_user(
            email="sales@alpha.test", password="passw0rd123",
            company=self.company, role=sales, branch=branch,
        )
        c = self.client_class()
        c.post(reverse("auth-login"), {
            "email": "sales@alpha.test",
            "password": "passw0rd123",
            "device_id": "TEST",
        })
        self.assertEqual(
            c.get(reverse("tax-profile")).status_code, status.HTTP_403_FORBIDDEN
        )

    def test_cannot_render_other_company_invoice(self):
        other = Company.objects.create(name="Beta")
        inv_b = Invoice.objects.create(
            company=other,
            warehouse=Warehouse.objects.create(company=other, name="BW"),
            number=1, total=Decimal("5"),
        )
        resp = self.client.get(reverse("invoice-document", args=[inv_b.id]))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_profile_reflects_default_country(self):
        resp = self.client.get(reverse("tax-profile"))
        self.assertEqual(resp.data["country"], "SD")
        self.assertEqual(resp.data["invoice_format"], TaxProfile.INVOICE_FORMAT_SIMPLE)
