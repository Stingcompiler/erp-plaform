"""Nightly maintenance for the audit trail.

Runs from the same scheduler as the daily scans (erp-daily-scans cron, the
standalone timer, or Celery beat). Moves ActivityLog rows past the
retention window into ActivityLogArchive in bounded batches, so the hot
table that backs the live log page stays small while the trail itself is
never discarded.
"""

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone


# The audit trail is the security record; a misconfigured retention env var
# must not be able to sweep last week's rows out of the live views.
MIN_RETENTION_DAYS = 30
BATCH_SIZE = 5000


@shared_task
def archive_activity_logs(days=None, batch_size=BATCH_SIZE):
    from core.models import ActivityLog, ActivityLogArchive

    if days is None:
        days = getattr(settings, "ACTIVITY_LOG_RETENTION_DAYS", 365)
    days = max(int(days), MIN_RETENTION_DAYS)
    cutoff = timezone.now() - timezone.timedelta(days=days)

    archived = 0
    while True:
        with transaction.atomic():
            rows = list(
                ActivityLog.objects.filter(created_at__lt=cutoff)
                .order_by("pk")
                .values(
                    "pk", "company_id", "user_id", "action", "entity_type",
                    "entity_id", "ip_address", "metadata", "created_at",
                )[:batch_size]
            )
            if not rows:
                break
            ActivityLogArchive.objects.bulk_create(
                [
                    ActivityLogArchive(
                        source_id=row["pk"],
                        company_id=row["company_id"],
                        user_id=row["user_id"],
                        action=row["action"],
                        entity_type=row["entity_type"],
                        entity_id=row["entity_id"],
                        ip_address=row["ip_address"],
                        metadata=row["metadata"],
                        created_at=row["created_at"],
                    )
                    for row in rows
                ],
                # A batch interrupted between copy and delete re-copies the
                # same rows on the next run; unique source_id makes that a
                # no-op instead of a duplicate.
                ignore_conflicts=True,
            )
            ActivityLog.objects.filter(pk__in=[row["pk"] for row in rows]).delete()
            archived += len(rows)
    return {"archived": archived, "retention_days": days, "cutoff": cutoff.isoformat()}
