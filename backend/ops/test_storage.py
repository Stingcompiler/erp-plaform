from decimal import Decimal

from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import Role, User
from inventory.models import Product
from ops import storage
from ops.models import BackupRecord
from org.models import Company


class FakeS3:
    def __init__(self):
        self.objects = {}

    def put_object(self, Bucket, Key, Body, ContentType):  # noqa: N803 - boto3 API
        self.objects[(Bucket, Key)] = Body

    def get_object(self, Bucket, Key):  # noqa: N803 - boto3 API
        body = self.objects[(Bucket, Key)]

        class _Body:
            def __init__(self, data):
                self._data = data

            def read(self):
                return self._data

        return {"Body": _Body(body)}


class StorageUnitTests(APITestCase):
    def test_disabled_when_no_bucket(self):
        with override_settings(BACKUP_S3_BUCKET=""):
            self.assertFalse(storage.is_enabled())
            self.assertIsNone(storage.upload_backup(1, "manual", "{}"))

    def test_build_key_shape(self):
        key = storage.build_key(7, "scheduled")
        self.assertTrue(key.startswith("backups/7/"))
        self.assertTrue(key.endswith("-scheduled.json"))

    def test_upload_uses_client_when_enabled(self):
        fake = FakeS3()
        original = storage._client
        storage._client = lambda: fake
        try:
            with override_settings(BACKUP_S3_BUCKET="my-bucket"):
                key = storage.upload_backup(3, "manual", '{"a":1}')
        finally:
            storage._client = original
        self.assertIsNotNone(key)
        self.assertEqual(len(fake.objects), 1)
        (bucket, stored_key), body = next(iter(fake.objects.items()))
        self.assertEqual(bucket, "my-bucket")
        self.assertEqual(stored_key, key)
        self.assertEqual(body, b'{"a":1}')

    def test_upload_failure_degrades_to_none(self):
        class Boom:
            def put_object(self, **kwargs):
                raise RuntimeError("network down")

        original = storage._client
        storage._client = lambda: Boom()
        try:
            with override_settings(BACKUP_S3_BUCKET="my-bucket"):
                key = storage.upload_backup(3, "manual", "{}")
        finally:
            storage._client = original
        self.assertIsNone(key)

    def test_download_returns_stored_payload(self):
        fake = FakeS3()
        original = storage._client
        storage._client = lambda: fake
        try:
            with override_settings(BACKUP_S3_BUCKET="my-bucket"):
                key = storage.upload_backup(3, "manual", '{"hello":"world"}')
                fetched = storage.download_backup(key)
        finally:
            storage._client = original
        self.assertEqual(fetched, '{"hello":"world"}')

    def test_download_disabled_returns_none(self):
        with override_settings(BACKUP_S3_BUCKET=""):
            self.assertIsNone(storage.download_backup("backups/1/x.json"))


class BackupStorageIntegrationTests(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        role = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123",
            company=self.company, role=role,
        )
        Product.objects.create(
            company=self.company, sku="SKU1", name="Widget", sale_price=Decimal("10")
        )
        r = self.client.post(
            reverse("auth-login"), {"email": "owner@alpha.test", "password": "passw0rd123"}
        )
        assert r.status_code == 200, r.content

    def test_backup_records_storage_key_when_enabled(self):
        fake = FakeS3()
        original = storage._client
        storage._client = lambda: fake
        try:
            with override_settings(BACKUP_S3_BUCKET="my-bucket"):
                resp = self.client.post(reverse("ops-backups"))
        finally:
            storage._client = original
        self.assertEqual(resp.status_code, 201, resp.content)
        record = BackupRecord.objects.get(company=self.company, kind="manual")
        self.assertTrue(record.storage_key)
        self.assertEqual(len(fake.objects), 1)

    def test_backup_has_no_storage_key_when_disabled(self):
        with override_settings(BACKUP_S3_BUCKET=""):
            resp = self.client.post(reverse("ops-backups"))
        self.assertEqual(resp.status_code, 201)
        record = BackupRecord.objects.get(company=self.company, kind="manual")
        self.assertEqual(record.storage_key, "")

    def test_restore_from_storage_key_into_empty_company(self):
        fake = FakeS3()
        original = storage._client
        storage._client = lambda: fake
        try:
            with override_settings(BACKUP_S3_BUCKET="my-bucket"):
                # Back up the source company (payload lands in fake storage).
                backup = self.client.post(reverse("ops-backups"))
                key = BackupRecord.objects.get(
                    company=self.company, kind="manual"
                ).storage_key
                self.assertTrue(key)

                # Fresh empty company + owner restores by key. Role names are
                # globally unique, so reuse the "Business Owner" role created in
                # setUp rather than creating a colliding duplicate.
                target = Company.objects.create(name="Target")
                role = Role.objects.get(name="Business Owner")
                User.objects.create_user(
                    email="owner@target.test", password="passw0rd123",
                    company=target, role=role,
                )
                tclient = self.client_class()
                tclient.post(
                    reverse("auth-login"),
                    {"email": "owner@target.test", "password": "passw0rd123"},
                )
                restore = tclient.post(
                    reverse("ops-restore"), {"storage_key": key}, format="json"
                )
        finally:
            storage._client = original
        self.assertEqual(restore.status_code, 200, restore.content)
        self.assertTrue(Product.objects.filter(company=target, sku="SKU1").exists())
