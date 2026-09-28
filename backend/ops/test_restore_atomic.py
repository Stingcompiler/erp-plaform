"""Review F19: a restore that fails midway used to leave the rows before the
failure behind, and the next attempt was refused because the company was no
longer empty. Now the dump is checked up front, the write is one
transaction, and a corrected file restores cleanly afterwards."""

from unittest import mock

from django.db import IntegrityError
from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import Role, User
from inventory.models import Category, Product
from ops.models import BackupRecord
from org.models import Company
from purchasing.models import Supplier
from sales.models import Customer


def good_dump():
    return {
        "version": 1,
        "master": {
            "categories": [{"id": 7, "name": "Drinks", "parent": None, "is_active": True}],
            "brands": [],
            "units": [{"id": 3, "name": "Piece", "symbol": "pc", "is_active": True}],
            "warehouses": [{"id": 1, "name": "Main", "code": "MAIN", "is_active": True}],
            "products": [
                {"id": 1, "sku": "A1", "name": "Cola", "category": 7, "unit": 3,
                 "cost_price": "1.50", "sale_price": "2.00"},
                {"id": 2, "sku": "A2", "name": "Water", "category": 7, "unit": 3,
                 "cost_price": "0.50", "sale_price": "1.00"},
            ],
            "customers": [{"id": 1, "name": "Ali", "phone": "0912"}],
            "suppliers": [{"id": 1, "name": "Nile Foods"}],
        },
        "transactional": {},
    }


class RestoreAtomicTests(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Fresh")
        role = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        User.objects.create_user(
            email="owner@fresh.test", password="passw0rd123", company=self.company, role=role,
        )
        login = self.client.post(reverse("auth-login"), {
            "email": "owner@fresh.test", "password": "passw0rd123", "device_id": "TEST",
        })
        assert login.status_code == 200, login.content

    def _restore(self, dump, **extra):
        return self.client.post(reverse("ops-restore"), {"data": dump, **extra}, format="json")

    def _assert_nothing_written(self):
        self.assertEqual(Product.objects.filter(company=self.company).count(), 0)
        self.assertEqual(Category.objects.filter(company=self.company).count(), 0)
        self.assertEqual(Customer.objects.filter(company=self.company).count(), 0)
        self.assertEqual(Supplier.objects.filter(company=self.company).count(), 0)
        self.assertFalse(BackupRecord.objects.filter(company=self.company).exists())

    def test_a_bad_row_is_named_and_nothing_is_written(self):
        dump = good_dump()
        del dump["master"]["products"][1]["name"]
        response = self._restore(dump)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.data["code"], "invalid_backup")
        self.assertEqual(response.data["section"], "products")
        self.assertEqual(response.data["row"], 2)
        self.assertEqual(response.data["field"], "name")
        self._assert_nothing_written()
        # The corrected file restores.
        fixed = self._restore(good_dump())
        self.assertEqual(fixed.status_code, 200, fixed.content)
        self.assertEqual(fixed.data["restored"], 4)
        self.assertEqual(Product.objects.filter(company=self.company).count(), 2)
        self.assertEqual(
            Product.objects.get(company=self.company, sku="A2").category.name, "Drinks"
        )

    def test_a_bad_price_is_named(self):
        dump = good_dump()
        dump["master"]["products"][0]["sale_price"] = "two"
        response = self._restore(dump)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual((response.data["section"], response.data["row"], response.data["field"]),
                         ("products", 1, "sale_price"))
        self._assert_nothing_written()

    def test_a_duplicate_inside_the_dump_is_named(self):
        dump = good_dump()
        dump["master"]["products"][1]["sku"] = "a1"
        response = self._restore(dump)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual((response.data["section"], response.data["row"], response.data["field"]),
                         ("products", 2, "sku"))
        self._assert_nothing_written()

    def test_sections_must_be_lists_of_rows(self):
        for master in ("not a dict", {"products": "rows"}, {"products": ["row"]}):
            response = self._restore({"version": 1, "master": master})
            self.assertEqual(response.status_code, 400, response.content)
            self.assertEqual(response.data["code"], "invalid_backup")
        self._assert_nothing_written()

    def test_a_failure_while_writing_rolls_everything_back(self):
        """What validation cannot foresee (a database refusal midway) must
        not leave half a restore behind either."""
        real_create = Product.objects.create
        calls = []

        def flaky(**kwargs):
            calls.append(kwargs["sku"])
            if len(calls) == 2:
                raise IntegrityError("simulated")
            return real_create(**kwargs)

        with mock.patch.object(Product.objects, "create", side_effect=flaky):
            response = self._restore(good_dump())
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.data["section"], "products")
        self.assertEqual(response.data["row"], 2)
        self._assert_nothing_written()
        retry = self._restore(good_dump())
        self.assertEqual(retry.status_code, 200, retry.content)
        self.assertEqual(Product.objects.filter(company=self.company).count(), 2)
