"""Deleting a company, deferred by 30 days.

``schedule_deletion`` is what the platform's "Delete company" button does,
at once and in one transaction:

* the company is deactivated (``is_active=False``): nobody signs in and every
  session ends (core.company_access), its public page /s/<slug>/ and its
  public API answer 404, and vezano.app/track stops listing its orders —
  those lookups already require an active company;
* the subscription stops (``cancelled``; the previous status is kept on the
  deletion record for an undo);
* a full backup is taken: the company transfer export (ops.transfer — every
  model the transfer archive carries, found from the model graph), stored
  where backups live (object storage when BACKUP_S3_* is configured, else
  gzip in the database, ops.snapshots) as an ops.BackupRecord of kind
  ``deletion``, kept at least until ``BACKUP_RETENTION_DAYS`` after the purge;
* ``purge_after`` is set to now + PURGE_DELAY_DAYS.

Until then the platform may restore (undo) or purge at once. The nightly
job (``purge_due`` from run_daily_scans / the purge_deleted_companies
command) purges what is due: every row of the company's data, deleted in
dependency order in one transaction per company, leaving the deletion row
as the tombstone (original id, name, slug, who, when, backup) — which also
keeps the slug from ever being reused (org.Company.save).
"""

import gzip
import io
import json
import logging
import zipfile
from collections import Counter
from datetime import timedelta

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError, RestrictedError
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework.exceptions import ValidationError

from core.activity import log_activity
from subscriptions.models import (
    CompanyDeletion,
    EntitlementOverride,
    PaymentAllocation,
    PlanChangeRequest,
    Subscription,
    SubscriptionEvent,
    SubscriptionInvoice,
    SubscriptionPayment,
)

logger = logging.getLogger(__name__)

PURGE_DELAY_DAYS = 30


class PurgeError(Exception):
    """A company's data could not be deleted completely (nothing was)."""


def retention_days():
    return max(int(getattr(settings, "BACKUP_RETENTION_DAYS", 30)), 1)


def confirmation_matches(company, typed):
    """The typed confirmation: the company's exact name or slug (spaces
    around it and letter case do not matter)."""
    typed = " ".join(str(typed or "").split()).casefold()
    if not typed:
        return False
    return typed in {
        " ".join(company.name.split()).casefold(), (company.slug or "").casefold(),
    }


def require_confirmation(company, typed):
    if not confirmation_matches(company, typed):
        raise ValidationError({
            "confirm": _("Type the company's name or its slug (%(slug)s) exactly to confirm.")
            % {"slug": company.slug},
            "code": "confirmation_mismatch",
        })


# ---------------------------------------------------------------- backup

def _take_backup(company, actor, keep_until):
    """Export the whole company and store it as a ``deletion`` backup."""
    from ops import storage
    from ops.models import BackupRecord
    from ops.transfer import export_company

    payload, _media = export_company(company, include_media=False)
    text = json.dumps(payload, cls=DjangoJSONEncoder, ensure_ascii=False)
    key = storage.upload_backup(company.pk, BackupRecord.DELETION, text)
    rows = sum(payload["counts"].values())
    record = BackupRecord.objects.create(
        company=company, kind=BackupRecord.DELETION, status=BackupRecord.SUCCESS,
        record_count=rows, size_bytes=len(text.encode("utf-8")),
        storage_key=key or "",
        payload_gz=None if key else gzip.compress(text.encode("utf-8")),
        keep_until=keep_until,
        note=f"Company deletion: {company.name} ({company.slug})"[:255],
        created_by=actor if actor is not None and actor.is_authenticated else None,
    )
    return record, rows


def backup_archive(deletion):
    """The deletion backup as a company transfer archive (zip with
    company.json and its manifest — what ``import_company`` reads), or None
    when its bytes are gone."""
    from ops import snapshots
    from ops.transfer import ARCHIVE_NAME, MANIFEST_NAME

    record = deletion.backup
    text = snapshots.read(record) if record is not None else None
    if not text:
        return None
    payload = json.loads(text)
    manifest = {
        "format_version": payload.get("format_version"),
        "application_version": payload.get("application_version"),
        "company": payload.get("source"),
        "counts": payload.get("counts"),
        "total_rows": sum((payload.get("counts") or {}).values()),
        "media_files": 0,
        "media_note": "Uploaded files are not included; they stay in media storage.",
        "deletion": {
            "requested_at": deletion.requested_at.isoformat(),
            "purge_after": deletion.purge_after.isoformat(),
        },
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(ARCHIVE_NAME, text)
        archive.writestr(
            MANIFEST_NAME,
            json.dumps(manifest, cls=DjangoJSONEncoder, indent=2, ensure_ascii=False),
        )
    return buffer.getvalue()


# ---------------------------------------------------------------- schedule / restore

def open_deletion(company):
    return CompanyDeletion.objects.filter(
        company=company, status=CompanyDeletion.SCHEDULED
    ).first()


@transaction.atomic
def schedule_deletion(company, actor, typed, reason="", request=None):
    from org.models import Company

    company = Company.objects.select_for_update().get(pk=company.pk)
    require_confirmation(company, typed)
    if open_deletion(company) is not None:
        raise ValidationError({"detail": _("This company is already scheduled for deletion.")})
    now = timezone.now()
    purge_after = now + timedelta(days=PURGE_DELAY_DAYS)
    backup, rows = _take_backup(
        company, actor, keep_until=purge_after + timedelta(days=retention_days())
    )
    subscription = Subscription.objects.select_for_update().filter(company=company).first()
    previous_status = subscription.status if subscription else ""
    if subscription is not None and subscription.status != Subscription.CANCELLED:
        subscription.status = Subscription.CANCELLED
        subscription.revision += 1
        subscription.save(update_fields=["status", "revision", "updated_at"])
        SubscriptionEvent.objects.create(
            subscription=subscription, event_type="company_deletion_scheduled",
            from_status=previous_status, to_status=Subscription.CANCELLED,
            reason=(reason or "")[:2000], actor=actor,
        )
    company.is_active = False
    company.save(update_fields=["is_active", "updated_at"])
    deletion = CompanyDeletion.objects.create(
        company=company, company_ref=company.pk, name=company.name, slug=company.slug,
        reason=(reason or "").strip()[:2000], requested_by=actor, purge_after=purge_after,
        subscription_status=previous_status, backup=backup, backup_rows=rows,
    )
    log_activity(
        action="company_deletion_scheduled", request=request, user=actor, company=company,
        entity_type="CompanyLifecycle", entity_id=company.pk,
        metadata={
            "company": company.name, "slug": company.slug, "company_id": company.pk,
            "purge_after": purge_after.isoformat(), "backup_id": backup.pk,
            "backup_rows": rows, "reason": deletion.reason,
        },
    )
    return deletion


@transaction.atomic
def restore_company(company, actor, request=None):
    from org.models import Company

    company = Company.objects.select_for_update().get(pk=company.pk)
    deletion = open_deletion(company)
    if deletion is None:
        raise ValidationError({"detail": _("This company is not scheduled for deletion.")})
    subscription = Subscription.objects.select_for_update().filter(company=company).first()
    if (
        subscription is not None and deletion.subscription_status
        and subscription.status != deletion.subscription_status
    ):
        previous = subscription.status
        subscription.status = deletion.subscription_status
        subscription.revision += 1
        subscription.save(update_fields=["status", "revision", "updated_at"])
        SubscriptionEvent.objects.create(
            subscription=subscription, event_type="company_deletion_cancelled",
            from_status=previous, to_status=subscription.status, actor=actor,
        )
    company.is_active = True
    company.save(update_fields=["is_active", "updated_at"])
    deletion.status = CompanyDeletion.RESTORED
    deletion.restored_by = actor
    deletion.restored_at = timezone.now()
    deletion.save(update_fields=["status", "restored_by", "restored_at"])
    log_activity(
        action="company_deletion_cancelled", request=request, user=actor, company=company,
        entity_type="CompanyLifecycle", entity_id=company.pk,
        metadata={"company": company.name, "slug": company.slug, "company_id": company.pk},
    )
    return deletion


# ---------------------------------------------------------------- purge

def _label(model):
    return f"{model._meta.app_label}.{model._meta.object_name}"


def _commercial_querysets(company):
    """The vendor's rows about the company. They sit outside the transfer
    graph (never exported), so they are removed first, children first:
    several of them PROTECT the company and its users."""
    return [
        PaymentAllocation.objects.filter(payment__company=company),
        PaymentAllocation.objects.filter(invoice__company=company),
        PlanChangeRequest.objects.filter(company=company),
        SubscriptionPayment.objects.filter(company=company),
        SubscriptionInvoice.objects.filter(company=company),
        SubscriptionEvent.objects.filter(subscription__company=company),
        EntitlementOverride.objects.filter(company=company),
        Subscription.objects.filter(company=company),
    ]


def _company_querysets(company, keep_backup_ids):
    """Every transferable model's rows of the company, dependants first.

    Kept on purpose: the platform team's own audit rows about the company
    (they lose the company link and keep its name in their metadata) and
    the deletion backup itself."""
    from accounts.platform_team import platform_members
    from core.models import ActivityLog
    from ops.models import BackupRecord
    from ops.transfer import company_queryset, transferable_models

    for model in reversed(transferable_models()):
        queryset = company_queryset(model, company)
        if model is ActivityLog:
            queryset = queryset.exclude(user__in=platform_members().values("pk"))
        elif model is BackupRecord:
            queryset = queryset.exclude(pk__in=keep_backup_ids)
        yield model, queryset


def _delete_all(querysets):
    """Delete each queryset, retrying the ones blocked by a protected
    reference until nothing is left or no pass makes progress."""
    counts = Counter()
    pending = list(querysets)
    while pending:
        blocked = []
        for model, queryset in pending:
            try:
                with transaction.atomic():
                    _total, per_model = queryset.delete()
            except (ProtectedError, RestrictedError, IntegrityError) as exc:
                blocked.append((model, queryset, exc))
                continue
            counts.update({label: n for label, n in per_model.items() if n})
        if len(blocked) == len(pending):
            names = ", ".join(_label(model) for model, _qs, _exc in blocked)
            raise PurgeError(f"Rows still referenced after every pass: {names}")
        pending = [(model, queryset) for model, queryset, _exc in blocked]
    return counts


def purge_company(deletion, actor=None, request=None):
    """Delete the company and all its data; the deletion row becomes the
    tombstone. One transaction: a failure deletes nothing."""
    from org.models import Company

    with transaction.atomic():
        deletion = CompanyDeletion.objects.select_for_update().get(pk=deletion.pk)
        if deletion.status != CompanyDeletion.SCHEDULED or deletion.company_id is None:
            raise ValidationError({"detail": _("This company is not scheduled for deletion.")})
        company = Company.objects.select_for_update().get(pk=deletion.company_id)
        keep = [deletion.backup_id] if deletion.backup_id else []
        counts = _delete_all(
            [(qs.model, qs) for qs in _commercial_querysets(company)]
            + list(_company_querysets(company, keep))
        )
        _total, per_model = Company.objects.filter(pk=company.pk).delete()
        counts.update({label: n for label, n in per_model.items() if n})
        now = timezone.now()
        deletion.refresh_from_db()
        deletion.status = CompanyDeletion.PURGED
        deletion.purged_at = now
        deletion.purged_by = actor
        deletion.purged_rows = dict(counts)
        deletion.save(update_fields=["status", "purged_at", "purged_by", "purged_rows"])
        if deletion.backup_id:
            # The backup outlives the purge by the retention window, whether
            # the purge came on schedule or early.
            from ops.models import BackupRecord

            keep_until = now + timedelta(days=retention_days())
            BackupRecord.objects.filter(pk=deletion.backup_id).exclude(
                keep_until__gt=keep_until
            ).update(keep_until=keep_until)
        log_activity(
            action="company_purged", request=request, user=actor, company=None,
            entity_type="CompanyLifecycle", entity_id=deletion.company_ref,
            metadata={
                "company": deletion.name, "slug": deletion.slug,
                "company_id": deletion.company_ref, "backup_id": deletion.backup_id,
                "rows_deleted": sum(counts.values()),
                "scheduled": actor is None,
            },
        )
    return deletion


def purge_due(now=None):
    """Purge every company whose 30 days are over. One company failing is
    logged and does not stop the others."""
    now = now or timezone.now()
    purged, failed = [], []
    due = CompanyDeletion.objects.filter(
        status=CompanyDeletion.SCHEDULED, purge_after__lte=now, company__isnull=False,
    ).order_by("purge_after")
    for deletion in due:
        try:
            purge_company(deletion)
            purged.append(deletion.company_ref)
        except Exception as exc:  # noqa: BLE001 - one company must not block the rest
            logger.exception("purge of company %s failed", deletion.company_ref)
            failed.append({"company_id": deletion.company_ref, "error": str(exc)[:300]})
    return {"purged": purged, "failed": failed}
