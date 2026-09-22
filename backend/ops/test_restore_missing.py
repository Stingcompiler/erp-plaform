"""Restoring into a company that is already working.

The disaster restore refuses a populated company on purpose. The everyday
case — someone deleted a product, a price list was lost — needs the opposite:
add what is missing, touch nothing that is there.
"""
from decimal import Decimal

from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import Role, User
from inventory.models import Brand, Category, Product, Warehouse
from org.models import Company
from sales.models import Customer


class RestoreMissingOnlyTests(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha Trading")
        role = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123",
            company=self.company, role=role,
        )
        category = Category.objects.create(company=self.company, name="مواد غذائية")
        Warehouse.objects.create(company=self.company, name="المخزن الرئيسي")
        Brand.objects.create(company=self.company, name="الوطنية")
        Product.objects.create(
            company=self.company, sku="SKU1", name="أرز بسمتي", category=category,
            cost_price=Decimal("6"), sale_price=Decimal("10"), barcode="6290000000001",
        )
        Product.objects.create(
            company=self.company, sku="SKU2", name="سكر", cost_price=Decimal("3"),
            sale_price=Decimal("5"),
        )
        Customer.objects.create(company=self.company, name="بقالة الحي")
        self.client.post(
            reverse("auth-login"),
            {"email": "owner@alpha.test", "password": "passw0rd123", "device_id": "TEST"},
        )
        self.backup = self.client.post(reverse("ops-backups")).data["data"]
        # Someone deletes a product and a customer, and the shop adds a new
        # product in the meantime with a price of its own.
        Product.objects.filter(sku="SKU2").delete()
        Customer.objects.filter(name="بقالة الحي").delete()
        Product.objects.filter(sku="SKU1").update(sale_price=Decimal("12"))

    def _restore(self, **body):
        return self.client.post(
            reverse("ops-restore"), {"data": self.backup, **body}, format="json",
        )

    def test_the_disaster_restore_still_refuses_a_working_company(self):
        response = self._restore()
        self.assertEqual(response.status_code, 400)

    def test_dry_run_says_what_it_would_add_and_writes_nothing(self):
        response = self._restore(mode="missing", dry_run=True)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["dry_run"])
        self.assertEqual(response.data["added"].get("products"), 1)
        self.assertEqual(response.data["added"].get("customers"), 1)
        self.assertEqual(response.data["skipped"].get("products"), 1)
        self.assertFalse(Product.objects.filter(sku="SKU2").exists())
        self.assertFalse(Customer.objects.exists())

    def test_missing_rows_come_back_and_live_rows_are_left_alone(self):
        response = self._restore(mode="missing")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["restored"], 2)
        self.assertTrue(Product.objects.filter(sku="SKU2").exists())
        self.assertTrue(Customer.objects.filter(name="بقالة الحي").exists())
        # The price the shop set after the backup is theirs, not the dump's.
        self.assertEqual(Product.objects.get(sku="SKU1").sale_price, Decimal("12"))
        # And no duplicate master rows appeared.
        self.assertEqual(Category.objects.filter(company=self.company).count(), 1)
        self.assertEqual(Warehouse.objects.filter(company=self.company).count(), 1)

    def test_running_it_again_changes_nothing(self):
        self._restore(mode="missing")
        before = Product.objects.count(), Customer.objects.count(), Category.objects.count()
        second = self._restore(mode="missing")
        self.assertEqual(second.data["restored"], 0)
        self.assertEqual(
            (Product.objects.count(), Customer.objects.count(), Category.objects.count()),
            before,
        )

    def test_a_barcode_already_in_use_is_never_duplicated(self):
        # Same item, different SKU in the dump: the barcode must still resolve
        # to one product, so it is skipped rather than inserted.
        Product.objects.filter(sku="SKU1").update(sku="SKU1-RENAMED")
        response = self._restore(mode="missing")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Product.objects.filter(barcode="6290000000001").count(), 1)

    def test_an_unknown_mode_is_refused(self):
        response = self._restore(mode="overwrite")
        self.assertEqual(response.status_code, 400)
        self.assertIn("mode", response.data)

    def test_names_match_the_way_a_person_reads_them(self):
        Category.objects.filter(company=self.company).update(name="  مواد   غذائية ")
        response = self._restore(mode="missing")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Category.objects.filter(company=self.company).count(), 1)

    def test_restoring_into_an_empty_company_still_replays_everything(self):
        empty = Company.objects.create(name="Fresh")
        role = Role.objects.get(name="Business Owner")
        User.objects.create_user(
            email="owner@fresh.test", password="passw0rd123", company=empty, role=role,
        )
        client = self.client_class()
        client.post(
            reverse("auth-login"),
            {"email": "owner@fresh.test", "password": "passw0rd123", "device_id": "F"},
        )
        response = client.post(
            reverse("ops-restore"), {"data": self.backup}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Product.objects.filter(company=empty).count(), 2)
