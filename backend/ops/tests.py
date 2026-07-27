from decimal import Decimal

from django.conf import settings
from django.core.management import call_command
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Role, User
from inventory.models import Product, Warehouse
from ops.models import BackupRecord, UserPreference
from org.models import Company


class OpsBase(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        self.owner = Role.objects.create(
            name="Business Owner", scope_level=Role.SCOPE_BUSINESS
        )
        self.user = User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123",
            company=self.company, role=self.owner,
        )
        Warehouse.objects.create(company=self.company, name="Main")
        Product.objects.create(
            company=self.company, sku="SKU1", name="Widget",
            cost_price=Decimal("6"), sale_price=Decimal("10"),
        )
        r = self.client.post(
            reverse("auth-login"), {"email": "owner@alpha.test", "password": "passw0rd123"}
        )
        assert r.status_code == 200, r.content


class BackupRestoreTests(OpsBase):
    def test_backup_creates_record_and_snapshot(self):
        resp = self.client.post(reverse("ops-backups"))
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        self.assertGreaterEqual(resp.data["backup"]["record_count"], 1)
        skus = {p["sku"] for p in resp.data["data"]["master"]["products"]}
        self.assertIn("SKU1", skus)
        self.assertTrue(
            BackupRecord.objects.filter(company=self.company, kind="manual").exists()
        )

    def test_backup_list(self):
        self.client.post(reverse("ops-backups"))
        resp = self.client.get(reverse("ops-backups"))
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.data), 1)

    def test_restore_into_empty_company(self):
        dump = self.client.post(reverse("ops-backups")).data["data"]
        # A fresh, empty company + its owner.
        target = Company.objects.create(name="Restored Co")
        User.objects.create_user(
            email="owner2@restored.test", password="passw0rd123",
            company=target, role=self.owner,
        )
        c = self.client_class()
        c.post(reverse("auth-login"), {"email": "owner2@restored.test", "password": "passw0rd123"})
        resp = c.post(reverse("ops-restore"), {"data": dump}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertTrue(Product.objects.filter(company=target, sku="SKU1").exists())

    def test_restore_refuses_nonempty_company(self):
        dump = self.client.post(reverse("ops-backups")).data["data"]
        # Caller's own company already has SKU1 -> restore must refuse.
        resp = self.client.post(reverse("ops-restore"), {"data": dump}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_scheduled_backup_command(self):
        call_command("run_scheduled_backup")
        self.assertTrue(
            BackupRecord.objects.filter(kind="scheduled", status="success").exists()
        )

    def test_backup_requires_settings_module(self):
        # A Sales Officer (no settings access) cannot back up.
        sales = Role.objects.create(name="Sales Officer", scope_level=Role.SCOPE_BRANCH)
        User.objects.create_user(
            email="sales@alpha.test", password="passw0rd123",
            company=self.company, role=sales,
        )
        c = self.client_class()
        c.post(reverse("auth-login"), {"email": "sales@alpha.test", "password": "passw0rd123"})
        self.assertEqual(
            c.post(reverse("ops-backups")).status_code, status.HTTP_403_FORBIDDEN
        )


class PreferenceTests(OpsBase):
    def test_get_default_preferences(self):
        resp = self.client.get(reverse("ops-preferences"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["language"], "en")
        self.assertEqual(resp.data["theme"], "system")
        self.assertEqual(resp.data["direction"], "ltr")

    def test_set_arabic_gives_rtl(self):
        resp = self.client.patch(
            reverse("ops-preferences"), {"language": "ar", "theme": "dark"},
            format="json",
        )
        self.assertEqual(resp.data["language"], "ar")
        self.assertEqual(resp.data["direction"], "rtl")
        self.assertEqual(resp.data["theme"], "dark")
        self.assertTrue(UserPreference.objects.filter(user=self.user).exists())

    def test_invalid_language_rejected(self):
        resp = self.client.patch(
            reverse("ops-preferences"), {"language": "fr"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_languages_list(self):
        resp = self.client.get(reverse("ops-languages"))
        codes = {lang["code"] for lang in resp.data}
        self.assertEqual(codes, {"en", "ar"})


class SecurityHardeningTests(OpsBase):
    def test_api_rejects_weak_password(self):
        resp = self.client.post(
            reverse("user-list"),
            {"email": "new@alpha.test", "password": "short"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_api_accepts_strong_password(self):
        resp = self.client.post(
            reverse("user-list"),
            {"email": "new@alpha.test", "password": "Str0ngPass!99"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)

    def test_refresh_token_rotation_enabled(self):
        self.assertTrue(settings.SIMPLE_JWT["ROTATE_REFRESH_TOKENS"])
        self.assertTrue(settings.SIMPLE_JWT["BLACKLIST_AFTER_ROTATION"])

    def test_security_headers_configured(self):
        self.assertTrue(settings.SECURE_CONTENT_TYPE_NOSNIFF)
        self.assertEqual(settings.X_FRAME_OPTIONS, "DENY")
