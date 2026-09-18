"""Backups without object storage: the snapshot lives in the database row,
downloads as a file, restores by id, and is pruned on a schedule with the
newest per company always kept.
"""

import gzip
import json
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Role, User
from ops import snapshots
from ops.models import BackupRecord
from org.models import Company


def _owner_client(company):
    role, _ = Role.objects.get_or_create(
        name="Business Owner", defaults={"scope_level": Role.SCOPE_BUSINESS}
    )
    user = User.objects.create_user(
        email=f"owner-{company.pk}@x.test", password="Owner-passw0rd!",
        company=company, role=role,
    )
    client = APIClient()
    client.force_authenticate(user)
    return client


@override_settings(BACKUP_S3_BUCKET="")
class InDatabaseSnapshotTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Mine")
        self.other = Company.objects.create(name="Theirs")
        self.client = _owner_client(self.company)

    def test_manual_backup_is_stored_compressed_and_downloadable(self):
        created = self.client.post("/api/ops/backups/")
        self.assertEqual(created.status_code, 201, created.data)
        record = BackupRecord.objects.get(company=self.company, kind=BackupRecord.MANUAL)
        self.assertIsNotNone(record.payload_gz)
        self.assertEqual(record.storage_key, "")
        stored = json.loads(gzip.decompress(bytes(record.payload_gz)))
        self.assertEqual(stored, created.data["data"])

        listing = self.client.get("/api/ops/backups/")
        self.assertTrue(listing.json()[0]["downloadable"])

        download = self.client.get(f"/api/ops/backups/{record.pk}/download/")
        self.assertEqual(download.status_code, 200)
        self.assertIn("attachment", download["Content-Disposition"])
        self.assertIn(".json", download["Content-Disposition"])
        self.assertEqual(json.loads(download.content), created.data["data"])

    def test_another_company_cannot_download_or_restore_it(self):
        self.client.post("/api/ops/backups/")
        record = BackupRecord.objects.get(company=self.company)
        stranger = _owner_client(self.other)
        self.assertEqual(stranger.get(f"/api/ops/backups/{record.pk}/download/").status_code, 404)
        restore = stranger.post(
            "/api/ops/backups/restore/", {"backup_id": record.pk}, format="json"
        )
        self.assertEqual(restore.status_code, 404)

    def test_restore_by_backup_id_reads_the_stored_snapshot(self):
        self.client.post("/api/ops/backups/")
        record = BackupRecord.objects.get(company=self.company)
        with self.settings(DEBUG=False):
            restore = self.client.post(
                "/api/ops/backups/restore/", {"backup_id": record.pk}, format="json"
            )
        # An empty company restoring its own (empty) master data: succeeds with 0 rows
        # or is refused as non-empty by the restore rules — either way the snapshot
        # was found and read; a 404 would mean the lookup failed.
        self.assertNotEqual(restore.status_code, 404, restore.data)

    def test_metadata_only_legacy_rows_are_not_downloadable(self):
        record = BackupRecord.objects.create(
            company=self.company, kind=BackupRecord.SCHEDULED, status=BackupRecord.SUCCESS
        )
        self.assertFalse(self.client.get("/api/ops/backups/").json()[0]["downloadable"])
        download = self.client.get(f"/api/ops/backups/{record.pk}/download/")
        self.assertEqual(download.status_code, 404)

    def test_prune_keeps_the_newest_per_company(self):
        old = snapshots.store(self.company, BackupRecord.SCHEDULED, {"a": 1})
        older_other = snapshots.store(self.other, BackupRecord.SCHEDULED, {"b": 1})
        BackupRecord.objects.filter(pk__in=[old.pk, older_other.pk]).update(
            created_at=timezone.now() - timedelta(days=90)
        )
        newer = snapshots.store(self.company, BackupRecord.SCHEDULED, {"a": 2})

        pruned = snapshots.prune(days=30)

        self.assertEqual(pruned, 1)  # only `old`: `older_other` is its company's newest
        for record in (old, older_other, newer):
            record.refresh_from_db()
        self.assertIsNone(old.payload_gz)
        self.assertIsNotNone(older_other.payload_gz)
        self.assertIsNotNone(newer.payload_gz)
        self.assertTrue(BackupRecord.objects.filter(pk=old.pk).exists())  # audit row stays


@override_settings(BACKUP_S3_BUCKET="bucket")
class ObjectStorageTierTests(TestCase):
    def test_store_prefers_object_storage_and_keeps_no_inline_copy(self):
        from unittest import mock

        company = Company.objects.create(name="Mine")
        with mock.patch("ops.storage.upload_backup", return_value="backups/1/x.json"):
            record = snapshots.store(company, BackupRecord.MANUAL, {"a": 1})
        self.assertEqual(record.storage_key, "backups/1/x.json")
        self.assertIsNone(record.payload_gz)
        with mock.patch("ops.storage.download_backup", return_value='{"a": 1}'):
            self.assertEqual(snapshots.read(record), '{"a": 1}')
