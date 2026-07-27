"""
Optional off-box storage for backup payloads (S3/R2-compatible).

Activated only when a bucket is configured via env — otherwise every function
is a safe no-op and the system behaves exactly as before (metadata-only
backups). `boto3` is imported lazily inside `_client()` so the dependency is
only needed when durable storage is actually turned on, and so tests can
monkeypatch `_client` without importing boto3 at all.
"""

import logging
from datetime import datetime, timezone

from django.conf import settings

logger = logging.getLogger(__name__)


def is_enabled():
    return bool(getattr(settings, "BACKUP_S3_BUCKET", "") or "")


def _client():  # pragma: no cover - thin boto3 wrapper, patched in tests
    import boto3

    kwargs = {}
    endpoint = getattr(settings, "BACKUP_S3_ENDPOINT_URL", "") or ""
    region = getattr(settings, "BACKUP_S3_REGION", "") or ""
    access = getattr(settings, "BACKUP_S3_ACCESS_KEY_ID", "") or ""
    secret = getattr(settings, "BACKUP_S3_SECRET_ACCESS_KEY", "") or ""
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    if region:
        kwargs["region_name"] = region
    if access and secret:
        kwargs["aws_access_key_id"] = access
        kwargs["aws_secret_access_key"] = secret
    return boto3.client("s3", **kwargs)


def build_key(company_id, kind):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    scope = company_id if company_id is not None else "platform"
    return f"backups/{scope}/{stamp}-{kind}.json"


def upload_backup(company_id, kind, payload):
    """
    Upload a JSON backup payload; return the object key on success, else None.
    Never raises — a storage failure must not break the backup audit record.
    """
    if not is_enabled():
        return None
    key = build_key(company_id, kind)
    try:
        client = _client()
        client.put_object(
            Bucket=settings.BACKUP_S3_BUCKET,
            Key=key,
            Body=payload.encode("utf-8") if isinstance(payload, str) else payload,
            ContentType="application/json",
        )
        return key
    except Exception as exc:  # noqa: BLE001 - report and degrade gracefully
        logger.error("Backup upload to object storage failed: %s", exc)
        return None


def download_backup(key):
    """
    Fetch a previously stored backup payload by key; return the JSON string on
    success, else None. Never raises.
    """
    if not is_enabled():
        return None
    try:
        client = _client()
        obj = client.get_object(Bucket=settings.BACKUP_S3_BUCKET, Key=key)
        body = obj["Body"].read()
        return body.decode("utf-8") if isinstance(body, bytes) else body
    except Exception as exc:  # noqa: BLE001 - report and degrade gracefully
        logger.error("Backup download from object storage failed: %s", exc)
        return None
