"""seed_demo fills a company through the real serializers/views and is
safe to run twice."""
import tempfile

from django.core.management import call_command
from django.test import TestCase, override_settings

from accounts.models import Role, User
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
