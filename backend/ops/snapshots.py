"""Where a backup's bytes live, and how they come back.

Two tiers, chosen per deployment by configuration, transparent to callers:
object storage (S3/R2) when BACKUP_S3_BUCKET is set, else the database
row itself (gzip in BackupRecord.payload_gz). Either way the owner gets a
downloadable, restorable file — the point of a backup.
"""

import gzip
import json

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone

from ops.models import BackupRecord


def store(company, kind, data, *, user=None):
    """Persist a dump and return its BackupRecord (always SUCCESS: a
    storage failure degrades to the database tier, never to metadata-only)."""
    from ops import storage
    from ops.services import count_records

    payload = json.dumps(data, cls=DjangoJSONEncoder)
    key = storage.upload_backup(company.id, kind, payload)
    return BackupRecord.objects.create(
        company=company, kind=kind, status=BackupRecord.SUCCESS,
        record_count=count_records(data), size_bytes=len(payload),
        storage_key=key or "",
        payload_gz=None if key else gzip.compress(payload.encode("utf-8")),
        created_by=user if user is not None and user.is_authenticated else None,
    )


def read(record):
    """The stored JSON text, or None when this record carries no payload."""
    if record.storage_key:
        from ops import storage

        return storage.download_backup(record.storage_key)
    if record.payload_gz is not None:
        return gzip.decompress(bytes(record.payload_gz)).decode("utf-8")
    return None


def prune(days=None):
    """Drop in-database payloads older than the retention window, keeping
    every company's newest successful snapshot regardless of age. The
    audit rows stay; only the bytes go."""
    days = getattr(settings, "BACKUP_RETENTION_DAYS", 30) if days is None else days
    cutoff = timezone.now() - timezone.timedelta(days=max(int(days), 1))
    keep = set(
        BackupRecord.objects.filter(status=BackupRecord.SUCCESS, payload_gz__isnull=False)
        .order_by("company_id", "-created_at")
        .distinct("company_id")
        .values_list("pk", flat=True)
    ) if _supports_distinct_on() else _newest_per_company()
    stale = BackupRecord.objects.filter(
        payload_gz__isnull=False, created_at__lt=cutoff
    ).exclude(pk__in=keep)
    return stale.update(payload_gz=None)


def _supports_distinct_on():
    from django.db import connection

    return connection.vendor == "postgresql"


def _newest_per_company():
    newest = {}
    rows = BackupRecord.objects.filter(
        status=BackupRecord.SUCCESS, payload_gz__isnull=False
    ).order_by("-created_at").values_list("pk", "company_id")
    for pk, company_id in rows:
        newest.setdefault(company_id, pk)
    return set(newest.values())
