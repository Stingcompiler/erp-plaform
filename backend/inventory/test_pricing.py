"""Inflation pricing: reference prices, the daily rate, and bulk repricing."""
from decimal import Decimal

from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import Role, User
from inventory.models import Category, Product
from inventory.pricing import round_to_step
from org.models import Branch, Company, ExchangeRate


class RoundingTests(APITestCase):
    def test_rounds_half_up_to_the_step(self):
        self.assertEqual(round_to_step(Decimal("84317.4"), "1"), Decimal("84317.00"))
        self.assertEqual(round_to_step(Decimal("84317.5"), "1"), Decimal("84318.00"))
        self.assertEqual(round_to_step(Decimal("84317"), "100"), Decimal("84300.00"))
        self.assertEqual(round_to_step(Decimal("84350"), "100"), Decimal("84400.00"))
        self.assertEqual(round_to_step(Decimal("1.005"), "0.01"), Decimal("1.01"))


class PricingBase(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        self.other = Company.objects.create(name="Beta")
        self.branch = Branch.objects.create(company=self.company, name="Main")
        self.owner = User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123", company=self.company,
            role=Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS),
        )
        self.clerk = User.objects.create_user(
            email="clerk@alpha.test", password="passw0rd123", company=self.company,
            branch=self.branch,
            role=Role.objects.create(name="Inventory Officer", scope_level=Role.SCOPE_BRANCH),
        )
        self.food = Category.objects.create(company=self.company, name="Food")
        self.sugar = Product.objects.create(
            company=self.company, sku="SUG", name="Sugar 50kg", category=self.food,
            reference_price=Decimal("50"), sale_price=Decimal("350000"),
            cost_price=Decimal("300000"),
        )
        self.oil = Product.objects.create(
            company=self.company, sku="OIL", name="Oil 20L", category=self.food,
            reference_price=Decimal("30.5"), sale_price=Decimal("200000"),
        )
        # No reference price: a rate reprice must leave it alone.
        self.bag = Product.objects.create(
            company=self.company, sku="BAG", name="Bag", sale_price=Decimal("500"),
        )
        Product.objects.create(
            company=self.other, sku="SUG", name="Other sugar",
            reference_price=Decimal("50"), sale_price=Decimal("1"),
        )

    def _as(self, user):
        self.client.force_authenticate(user)

    def _record_rate(self, rate, user=None):
        self._as(user or self.owner)
        return self.client.post(
            reverse("exchangerate-list"), {"rate": rate}, format="json"
        )


class ExchangeRateTests(PricingBase):
    def test_recording_a_rate_updates_the_company_and_keeps_history(self):
        first = self._record_rate("6000")
        self.assertEqual(first.status_code, 201, first.data)
        second = self._record_rate("8400.5")
        self.assertEqual(second.status_code, 201, second.data)
        self.company.refresh_from_db()
        self.assertEqual(self.company.exchange_rate, Decimal("8400.5000"))
        self.assertIsNotNone(self.company.exchange_rate_at)
        self.assertEqual(ExchangeRate.objects.filter(company=self.company).count(), 2)
        listing = self.client.get(reverse("exchangerate-list")).data["results"]
        self.assertEqual([row["rate"] for row in listing], ["8400.5000", "6000.0000"])
        self.assertEqual(listing[0]["currency"], "USD")
        profile = self.client.get(reverse("company-profile")).data
        self.assertEqual(profile["exchange_rate"], Decimal("8400.5000"))
        self.assertEqual(profile["reference_currency"], "USD")

    def test_only_approvers_record_rates_and_the_rate_must_be_positive(self):
        self.assertEqual(self._record_rate("8400", user=self.clerk).status_code, 403)
        self.assertEqual(self._record_rate("0").status_code, 400)
        self.assertEqual(self._record_rate("-1").status_code, 400)

    def test_reference_currency_is_editable_and_normalised(self):
        self._as(self.owner)
        r = self.client.patch(
            reverse("company-profile"), {"reference_currency": " sar "}, format="json"
        )
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["reference_currency"], "SAR")
        self.assertEqual(self._record_rate("1000").data["currency"], "SAR")


class RepriceTests(PricingBase):
    def _reprice(self, body, user=None):
        self._as(user or self.owner)
        return self.client.post(reverse("product-reprice"), body, format="json")

    def test_reprice_by_rate_uses_reference_prices_and_rounds(self):
        self._record_rate("8400")
        r = self._reprice({"mode": "rate", "step": "100"})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual((r.data["matched"], r.data["changed"], r.data["skipped"]), (2, 2, 0))
        self.sugar.refresh_from_db()
        self.oil.refresh_from_db()
        self.bag.refresh_from_db()
        self.assertEqual(self.sugar.sale_price, Decimal("420000.00"))
        # 30.5 × 8400 = 256,200 → already on the 100 step.
        self.assertEqual(self.oil.sale_price, Decimal("256200.00"))
        self.assertEqual(self.bag.sale_price, Decimal("500.00"))
        # Cost untouched when only the sale price is targeted.
        self.assertEqual(self.sugar.cost_price, Decimal("300000.00"))
        self.assertEqual(
            Product.objects.get(company=self.other, sku="SUG").sale_price, Decimal("1.00")
        )

    def test_reprice_by_rate_needs_a_rate(self):
        r = self._reprice({"mode": "rate"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("rate", r.data)
        r = self._reprice({"mode": "rate", "rate": "9000", "step": "1000"})
        self.assertEqual(r.status_code, 200, r.data)
        self.sugar.refresh_from_db()
        self.assertEqual(self.sugar.sale_price, Decimal("450000.00"))

    def test_reprice_by_percent_scales_everything_including_unreferenced(self):
        r = self._reprice({"mode": "percent", "percent": "10", "step": "1"})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["changed"], 3)
        self.bag.refresh_from_db()
        self.assertEqual(self.bag.sale_price, Decimal("550.00"))

    def test_reprice_both_moves_cost_in_proportion(self):
        r = self._reprice({"mode": "rate", "rate": "8400", "target": "both", "step": "1"})
        self.assertEqual(r.status_code, 200, r.data)
        self.sugar.refresh_from_db()
        self.assertEqual(self.sugar.sale_price, Decimal("420000.00"))
        # 300000 × 420000 / 350000
        self.assertEqual(self.sugar.cost_price, Decimal("360000.00"))

    def test_dry_run_previews_without_writing(self):
        before = self.sugar.updated_at
        r = self._reprice({"mode": "rate", "rate": "8400", "dry_run": True, "step": "1"})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(r.data["dry_run"])
        self.assertEqual(r.data["changed"], 2)
        sample = {row["sku"]: row for row in r.data["sample"]}
        self.assertEqual(sample["SUG"]["after"]["sale_price"], Decimal("420000.00"))
        self.sugar.refresh_from_db()
        self.assertEqual(self.sugar.sale_price, Decimal("350000.00"))
        self.assertEqual(self.sugar.updated_at, before)

    def test_reprice_touches_updated_at_so_offline_tills_pull_it(self):
        before = self.sugar.updated_at
        self._reprice({"mode": "rate", "rate": "8400", "step": "1"})
        self.sugar.refresh_from_db()
        self.assertGreater(self.sugar.updated_at, before)

    def test_category_filter_and_role_guard(self):
        r = self._reprice({"mode": "percent", "percent": "5", "category": self.food.pk})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["matched"], 2)
        self.bag.refresh_from_db()
        self.assertEqual(self.bag.sale_price, Decimal("500.00"))
        self.assertEqual(
            self._reprice({"mode": "percent", "percent": "5"}, user=self.clerk).status_code, 403
        )
        self.assertEqual(self._reprice({"mode": "percent", "percent": "-100"}).status_code, 400)

    def test_product_list_shows_the_suggested_price(self):
        self._record_rate("8400")
        rows = {r["sku"]: r for r in self.client.get(reverse("product-list")).data["results"]}
        self.assertEqual(Decimal(rows["SUG"]["suggested_price"]), Decimal("420000"))
        self.assertEqual(Decimal(rows["SUG"]["reference_price"]), Decimal("50"))
        self.assertIsNone(rows["BAG"]["suggested_price"])
        r = self.client.patch(
            reverse("product-detail", args=[self.bag.pk]), {"reference_price": "-1"},
            format="json",
        )
        self.assertEqual(r.status_code, 400)
