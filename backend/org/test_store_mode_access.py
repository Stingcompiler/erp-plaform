"""Operating mode controls access without mutating preserved accounts."""

from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import Role, User
from org.models import Company, StoreModeAccessException


class StoreModeAccessTests(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Mode shop")
        self.owner_role = Role.objects.create(
            name="Business Owner", scope_level=Role.SCOPE_BUSINESS
        )
        self.sales_role = Role.objects.create(
            name="Sales Officer", scope_level=Role.SCOPE_BRANCH
        )
        self.cfo_role = Role.objects.create(
            name="Chief Financial Officer", scope_level=Role.SCOPE_BUSINESS
        )
        self.owner = User.objects.create_user(
            email="owner@modes.test", password="passw0rd12345",
            company=self.company, role=self.owner_role,
        )
        self.sales = User.objects.create_user(
            email="sales@modes.test", password="passw0rd12345",
            company=self.company, role=self.sales_role,
        )
        self.cfo = User.objects.create_user(
            email="cfo@modes.test", password="passw0rd12345",
            company=self.company, role=self.cfo_role,
        )
        self.client.force_authenticate(self.owner)

    def mode(self, business_type):
        return self.client.patch(
            reverse("company-profile"), {"business_type": business_type}, format="json"
        )

    def login_as(self, user):
        client = self.client_class()
        return client.post(
            reverse("auth-login"),
            {"email": user.email, "password": "passw0rd12345"},
            format="json",
        )

    def test_only_owner_can_change_operating_mode(self):
        self.client.force_authenticate(self.cfo)
        response = self.mode("shop")
        self.assertEqual(response.status_code, 403, response.data)
        self.company.refresh_from_db()
        self.assertEqual(self.company.business_type, Company.TYPE_ENTERPRISE)

        self.client.force_authenticate(self.owner)
        self.assertEqual(self.mode("shop").status_code, 200)

    def test_store_mode_blocks_non_store_account_without_deactivating_it(self):
        self.mode("shop")
        blocked = self.login_as(self.cfo)
        self.assertEqual(blocked.status_code, 403, blocked.data)
        self.assertEqual(blocked.data["code"], "store_mode_restricted")
        self.cfo.refresh_from_db()
        self.assertTrue(self.cfo.is_active)
        self.assertEqual(self.login_as(self.sales).status_code, 200)

    def test_owner_can_allow_a_user_or_role_as_an_exception(self):
        self.mode("shop")
        response = self.client.patch(
            reverse("store-mode-settings"),
            {"additional_user_ids": [self.cfo.id], "additional_role_ids": []},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(
            StoreModeAccessException.objects.filter(
                company=self.company, user=self.cfo
            ).exists()
        )
        self.assertEqual(self.login_as(self.cfo).status_code, 200)

    def test_company_mode_restores_access_automatically(self):
        self.mode("shop")
        self.assertEqual(self.login_as(self.cfo).status_code, 403)
        self.assertEqual(self.mode("enterprise").status_code, 200)
        self.assertEqual(self.login_as(self.cfo).status_code, 200)

    def test_store_mode_configuration_is_owner_only(self):
        self.client.force_authenticate(self.cfo)
        self.assertEqual(self.client.get(reverse("store-mode-settings")).status_code, 403)
        self.assertEqual(
            self.client.patch(
                reverse("store-mode-settings"),
                {"additional_user_ids": [], "additional_role_ids": [self.cfo_role.id]},
                format="json",
            ).status_code,
            403,
        )
