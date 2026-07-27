"""
Shop mode and the friction it removes.

`business_type` is a presentation preset, not a permission. These tests pin the
part that must never drift: switching it changes what a client *shows*, and
nothing about what the server *allows*. Plus the auto-SKU, which exists because
a shopkeeper thinks in barcodes and shouldn't have to invent a stock-keeping
unit before saving their first product.
"""

from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import Role, User
from core.rbac import access_map
from inventory.models import Product
from org.models import Company


class BusinessTypeTests(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Corner Shop")
        self.role = Role.objects.create(
            name="Business Owner", scope_level=Role.SCOPE_BUSINESS
        )
        self.user = User.objects.create_user(
            email="owner@shop.test", password="passw0rd12345",
            company=self.company, role=self.role,
        )
        self.client.force_authenticate(self.user)

    def test_existing_companies_default_to_enterprise(self):
        """Nobody loses screens on upgrade; a shop opts in."""
        self.assertEqual(self.company.business_type, Company.TYPE_ENTERPRISE)

    def test_a_new_company_has_not_chosen_yet(self):
        """The default and a deliberate choice must be distinguishable —
        otherwise nothing can know to ask, which is how shop mode stayed
        invisible to the shops it was built for."""
        self.assertFalse(self.company.business_type_chosen)

    def test_me_reports_the_unanswered_question(self):
        resp = self.client.get(reverse("auth-me"))
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertFalse(resp.data["business_type_chosen"])

    def test_choosing_a_type_settles_the_question(self):
        self.client.patch(
            reverse("company-profile"), {"business_type": "shop"}, format="json"
        )
        self.company.refresh_from_db()
        self.assertTrue(self.company.business_type_chosen)
        self.assertFalse(
            self.client.get(reverse("auth-me")).data["business_type_chosen"]
            is False
        )

    def test_confirming_the_default_also_settles_it(self):
        """Picking 'enterprise' is an answer, not a non-answer — the prompt
        must not keep reappearing for someone who chose to stay put."""
        resp = self.client.patch(
            reverse("company-profile"),
            {"business_type": "enterprise"}, format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.company.refresh_from_db()
        self.assertTrue(self.company.business_type_chosen)

    def test_the_flag_cannot_be_set_directly(self):
        """It is a consequence of answering, never something a client posts —
        otherwise the question could be dismissed without being answered."""
        self.client.patch(
            reverse("company-profile"),
            {"business_type_chosen": True}, format="json",
        )
        self.company.refresh_from_db()
        self.assertFalse(self.company.business_type_chosen)

    def test_the_profile_reports_it(self):
        resp = self.client.get(reverse("company-profile"))
        self.assertIn("business_type_chosen", resp.data)
        self.assertFalse(resp.data["business_type_chosen"])

    def test_a_rejected_type_leaves_the_question_open(self):
        self.client.patch(
            reverse("company-profile"),
            {"business_type": "franchise"}, format="json",
        )
        self.company.refresh_from_db()
        self.assertFalse(self.company.business_type_chosen)

    def test_a_company_less_user_is_never_asked(self):
        """A platform admin has no company to configure."""
        admin = User.objects.create_user(
            email="plat@nowhere.test", password="passw0rd12345",
            is_superuser=True,
        )
        self.client.force_authenticate(admin)
        resp = self.client.get(reverse("auth-me"))
        self.assertTrue(resp.data["business_type_chosen"])

    def test_owner_can_switch_to_shop(self):
        resp = self.client.patch(
            reverse("company-profile"), {"business_type": "shop"}, format="json"
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.company.refresh_from_db()
        self.assertEqual(self.company.business_type, "shop")

    def test_an_unknown_type_is_refused(self):
        resp = self.client.patch(
            reverse("company-profile"), {"business_type": "franchise"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400, resp.data)
        self.company.refresh_from_db()
        self.assertEqual(self.company.business_type, Company.TYPE_ENTERPRISE)

    def test_it_is_reported_on_me_so_the_shell_paints_once(self):
        self.client.patch(
            reverse("company-profile"), {"business_type": "shop"}, format="json"
        )
        # force_authenticate holds one in-memory user whose `company` relation
        # is cached from setUp; a real request loads the user fresh, so re-auth
        # with a fresh instance rather than asserting against a stale cache.
        self.client.force_authenticate(User.objects.get(pk=self.user.pk))
        resp = self.client.get(reverse("auth-me"))
        self.assertEqual(resp.data["business_type"], "shop")

    def test_switching_changes_no_permission(self):
        """The whole design rests on this: shop mode hides pages, it does not
        take rights away. If it ever did, growing out of shop mode would become
        a migration instead of a toggle."""
        before = access_map(self.user)
        self.client.patch(
            reverse("company-profile"), {"business_type": "shop"}, format="json"
        )
        self.user.refresh_from_db()
        self.assertEqual(access_map(self.user), before)

    def test_hidden_modules_are_still_reachable_by_api(self):
        """Shop mode is a client-side preset. A hidden page must still answer,
        or the toggle would silently become an access control."""
        self.client.patch(
            reverse("company-profile"), {"business_type": "shop"}, format="json"
        )
        for route in ("lead-list", "employee-list", "branch-list"):
            self.assertEqual(
                self.client.get(reverse(route)).status_code, 200, route
            )

    def test_a_role_without_settings_cannot_switch_it(self):
        clerk_role = Role.objects.create(
            name="Sales Officer", scope_level=Role.SCOPE_BRANCH
        )
        clerk = User.objects.create_user(
            email="clerk@shop.test", password="passw0rd12345",
            company=self.company, role=clerk_role,
        )
        self.client.force_authenticate(clerk)
        resp = self.client.patch(
            reverse("company-profile"), {"business_type": "shop"}, format="json"
        )
        self.assertEqual(resp.status_code, 403, resp.data)


class AutoSkuTests(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Corner Shop")
        self.role = Role.objects.create(
            name="Inventory Officer", scope_level=Role.SCOPE_BRANCH
        )
        self.user = User.objects.create_user(
            email="stock@shop.test", password="passw0rd12345",
            company=self.company, role=self.role,
        )
        self.client.force_authenticate(self.user)

    def _create(self, **extra):
        body = {"name": "Rice", "sale_price": "10", "barcode": ""}
        body.update(extra)
        return self.client.post(reverse("product-list"), body, format="json")

    def test_a_blank_sku_is_filled_in(self):
        resp = self._create()
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertTrue(resp.data["sku"])

    def test_generated_skus_do_not_collide(self):
        first = self._create(name="Rice").data["sku"]
        second = self._create(name="Sugar").data["sku"]
        self.assertNotEqual(first, second)

    def test_a_supplied_sku_is_respected(self):
        resp = self._create(sku="MYCODE")
        self.assertEqual(resp.data["sku"], "MYCODE")

    def test_generation_skips_a_hand_typed_collision(self):
        """A shop that typed 'P000001' by hand must not block the allocator."""
        Product.objects.create(
            company=self.company, sku="P000001", name="Taken"
        )
        resp = self._create()
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertNotEqual(resp.data["sku"], "P000001")

    def test_editing_never_regenerates_the_sku(self):
        """The code may already be printed on a shelf label."""
        created = self._create()
        sku = created.data["sku"]
        resp = self.client.patch(
            reverse("product-detail", args=[created.data["id"]]),
            {"name": "Rice 5kg"}, format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["sku"], sku)

    def test_skus_are_unique_only_within_a_company(self):
        other = Company.objects.create(name="Other Shop")
        other_user = User.objects.create_user(
            email="s@other.test", password="passw0rd12345",
            company=other, role=self.role,
        )
        mine = self._create().data["sku"]
        self.client.force_authenticate(other_user)
        theirs = self._create().data["sku"]
        # Two tenants numbering from their own counters is correct — and must
        # not raise.
        self.assertTrue(mine and theirs)
