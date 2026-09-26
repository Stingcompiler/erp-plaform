"""seed_demo fills a company through the real serializers/views and is
safe to run twice."""
import tempfile
from decimal import Decimal

from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from accounts.models import Role, User
from core.management.commands.seed_demo import _scaled
from crm.models import Lead
from inventory.models import Product
from org.models import Branch, Company
from sales.models import Customer, Invoice, Payment
from website.models import PlatformLead, RegistrationRequest, Website
from website.serializers import completeness


class SeedDemoTests(TestCase):
    def setUp(self):
        call_command("seed_roles", verbosity=0)
        self.company = Company.objects.create(name="Demo Co", email="demo@co.test")
        self.branch = Branch.objects.create(company=self.company, code="MAIN", name="Main")
        self.owner = User.objects.create_user(
            "owner@demo.test", "secure-password", company=self.company, branch=self.branch,
            role=Role.objects.get(name="Business Owner"),
        )

    def test_seeds_company_idempotently_and_platform_inbox(self):
        with tempfile.TemporaryDirectory() as media:
            with override_settings(MEDIA_ROOT=media):
                call_command("seed_demo", owner="owner@demo.test", sales=12, days=10, yes=True,
                             verbosity=0)
                self.assertEqual(Product.objects.filter(company=self.company).count(), 24)
                self.assertEqual(Customer.objects.filter(company=self.company).count(), 8)
                invoices = Invoice.objects.filter(company=self.company)
                self.assertEqual(invoices.count(), 12)
                self.assertTrue(Payment.objects.filter(company=self.company).exists())
                self.assertTrue(any(inv.amount_due() > 0 for inv in invoices))
                site = Website.objects.get(company=self.company)
                self.assertTrue(site.is_published)
                self.assertEqual(completeness(site), [])
                self.assertEqual(site.featured_products.count(), 6)
                # A seeded company is labelled a demo on its public page.
                self.company.refresh_from_db()
                self.assertTrue(self.company.is_demo)
                # Second run: no duplicate master data, only more sales.
                call_command("seed_demo", owner="owner@demo.test", sales=3, yes=True,
                             verbosity=0)
                self.assertEqual(Product.objects.filter(company=self.company).count(), 24)
                self.assertEqual(Customer.objects.filter(company=self.company).count(), 8)
                self.assertEqual(Invoice.objects.filter(company=self.company).count(), 15)
                # A cover whose file was lost (row still names it) is regenerated.
                site.refresh_from_db()
                site.cover_image.storage.delete(site.cover_image.name)
                self.assertIn("cover_image", completeness(site))
                call_command("seed_demo", owner="owner@demo.test", sales=0, yes=True,
                             verbosity=0)
                site.refresh_from_db()
                self.assertEqual(completeness(site), [])
                call_command("seed_demo", platform=True, yes=True, verbosity=0)
                call_command("seed_demo", platform=True, yes=True, verbosity=0)
                self.assertEqual(PlatformLead.objects.count(), 3)
                self.assertEqual(RegistrationRequest.objects.count(), 2)

    def _product(self, sku):
        return Product.objects.get(company=self.company, sku=sku)

    def test_default_scale_keeps_catalogue_prices(self):
        with tempfile.TemporaryDirectory() as media:
            with override_settings(MEDIA_ROOT=media):
                call_command("seed_demo", owner="owner@demo.test", sales=0, yes=True,
                             verbosity=0)
        sugar = self._product("DEMO-001")
        self.assertEqual((sugar.cost_price, sugar.sale_price), (Decimal("0.90"), Decimal("1.20")))
        self.assertEqual(Lead.objects.get(company=self.company, name="موزع الشرق")
                         .estimated_value, Decimal("70000"))

    def test_scale_converts_prices_to_shop_figures(self):
        """--scale 2500 (Sudanese pounds per dollar): prices become round
        SDG figures, every product still sells above cost, and sales go
        through at those prices."""
        with tempfile.TemporaryDirectory() as media:
            with override_settings(MEDIA_ROOT=media):
                call_command("seed_demo", "--scale", "2500", owner="owner@demo.test", sales=5,
                             yes=True, verbosity=0)
        sugar, water = self._product("DEMO-001"), self._product("DEMO-009")
        self.assertEqual((sugar.cost_price, sugar.sale_price), (Decimal(2250), Decimal(3000)))
        self.assertEqual(water.sale_price, Decimal(1000))
        for product in Product.objects.filter(company=self.company):
            self.assertEqual(product.sale_price % 5, 0, product.name)
            self.assertLess(product.cost_price, product.sale_price, product.name)
        self.assertEqual(Lead.objects.get(company=self.company, name="موزع الشرق")
                         .estimated_value, Decimal(175_000_000))
        invoices = Invoice.objects.filter(company=self.company)
        self.assertEqual(invoices.count(), 5)
        self.assertTrue(all(inv.total >= 1000 for inv in invoices))

    def test_scale_rounding_and_validation(self):
        self.assertEqual(_scaled("0.55", Decimal(2500)), Decimal(1400))   # 1375 → 1400
        self.assertEqual(_scaled("0.25", Decimal(600)), Decimal(150))
        self.assertEqual(_scaled("0.03", Decimal(600)), Decimal(18))
        self.assertEqual(_scaled("0.10", Decimal("1.5")), Decimal("0.15"))
        self.assertEqual(_scaled("1.20", Decimal(1)), Decimal("1.20"))
        for bad in ("0", "-3", "abc", "nan"):
            with self.assertRaises(CommandError):
                call_command("seed_demo", f"--scale={bad}", owner="owner@demo.test", yes=True,
                             verbosity=0)
        self.assertFalse(Product.objects.filter(company=self.company).exists())
