"""Archival keeps the audit trail whole while shrinking the hot table.

The rules the task must never break: nothing younger than the retention
window leaves the hot table, everything older lands in the archive with its
fields intact, an interrupted run can be re-run without duplicating rows,
and a bad retention value cannot sweep recent history.
"""

from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import ActivityLog, ActivityLogArchive
from core.tasks import MIN_RETENTION_DAYS, archive_activity_logs


def _log(days_ago, **kwargs):
    row = ActivityLog.objects.create(
        action=kwargs.pop("action", "login"), metadata=kwargs.pop("metadata", {}), **kwargs
    )
    # created_at is auto_now_add; push it into the past explicitly.
    ActivityLog.objects.filter(pk=row.pk).update(
        created_at=timezone.now() - timedelta(days=days_ago)
    )
    return row.pk


class ActivityLogArchiveTests(TestCase):
    def test_old_rows_move_and_young_rows_stay(self):
        old_pk = _log(400, metadata={"ip": "10.0.0.9"}, entity_type="Invoice", entity_id="7")
        young_pk = _log(10)

        result = archive_activity_logs.run(days=365)

        self.assertEqual(result["archived"], 1)
        self.assertEqual(
            list(ActivityLog.objects.values_list("pk", flat=True)), [young_pk]
        )
        archived = ActivityLogArchive.objects.get()
        self.assertEqual(archived.source_id, old_pk)
        self.assertEqual(archived.action, "login")
        self.assertEqual(archived.entity_type, "Invoice")
        self.assertEqual(archived.entity_id, "7")
        self.assertEqual(archived.metadata, {"ip": "10.0.0.9"})

    def test_rerun_after_interruption_does_not_duplicate(self):
        pk = _log(400)
        archive_activity_logs.run(days=365)
        # Simulate the interruption case: the row is back in the hot table
        # (copy happened, delete did not) and the task runs again.
        ActivityLog.objects.create(id=pk, action="login")
        ActivityLog.objects.filter(pk=pk).update(
            created_at=timezone.now() - timedelta(days=400)
        )
        archive_activity_logs.run(days=365)
        self.assertEqual(ActivityLogArchive.objects.filter(source_id=pk).count(), 1)
        self.assertFalse(ActivityLog.objects.filter(pk=pk).exists())

    def test_retention_floor_protects_recent_rows(self):
        _log(15)
        result = archive_activity_logs.run(days=1)
        self.assertEqual(result["retention_days"], MIN_RETENTION_DAYS)
        self.assertEqual(ActivityLog.objects.count(), 1)
        self.assertEqual(ActivityLogArchive.objects.count(), 0)

    def test_batches_drain_completely(self):
        for _ in range(5):
            _log(400)
        result = archive_activity_logs.run(days=365, batch_size=2)
        self.assertEqual(result["archived"], 5)
        self.assertEqual(ActivityLogArchive.objects.count(), 5)
        self.assertEqual(ActivityLog.objects.filter().count(), 0)

    @override_settings(ACTIVITY_LOG_RETENTION_DAYS=90)
    def test_default_days_come_from_settings(self):
        _log(120)
        result = archive_activity_logs.run()
        self.assertEqual(result["retention_days"], 90)
        self.assertEqual(ActivityLogArchive.objects.count(), 1)
