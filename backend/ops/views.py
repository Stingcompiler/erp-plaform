import json

from django.conf import settings
from django.http import HttpResponse
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.activity import log_activity
from core.rbac import RoleModuleAccess
from ops import snapshots
from ops.models import BackupRecord, UserPreference
from ops import services
from ops.services import dump_company, restore_master


class BackupView(APIView):
    """
    GET  /api/ops/backups/  -> list backup/restore records (metadata).
    POST /api/ops/backups/  -> create a backup of the caller's company; returns
                               the record metadata plus the snapshot payload.
    Gated to the `settings` module (Business Owner / platform admin).
    """

    permission_classes = [IsAuthenticated, RoleModuleAccess]
    rbac_module = "settings"

    def get(self, request):
        company_id = getattr(request.user, "company_id", None)
        records = BackupRecord.objects.filter(company_id=company_id).only(
            "id", "kind", "status", "record_count", "size_bytes",
            "storage_key", "created_at",
        ).defer("payload_gz")
        return Response([
            {
                "id": r.id, "kind": r.kind, "status": r.status,
                "record_count": r.record_count, "size_bytes": r.size_bytes,
                "storage_key": r.storage_key, "created_at": r.created_at,
                # A payload exists somewhere the API can read it back from.
                "downloadable": bool(r.storage_key) or BackupRecord.objects.filter(
                    pk=r.pk, payload_gz__isnull=False
                ).exists(),
            }
            for r in records
        ])

    def post(self, request):
        from org.models import Company
        company_id = getattr(request.user, "company_id", None)
        if company_id is None:
            return Response(
                {"detail": "A company-scoped user is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        company = Company.objects.get(pk=company_id)
        data = dump_company(company)
        record = snapshots.store(company, BackupRecord.MANUAL, data, user=request.user)
        log_activity(
            action="create", request=request, entity_type="BackupRecord",
            entity_id=record.id, metadata={"kind": "manual"},
        )
        return Response(
            {
                "backup": {
                    "id": record.id, "record_count": record.record_count,
                    "size_bytes": record.size_bytes,
                    "created_at": record.created_at.isoformat(),
                },
                "data": data,
            },
            status=status.HTTP_201_CREATED,
        )


class RestoreView(APIView):
    """
    POST /api/ops/backups/restore/  body: {"data": <dump>}
    Restores master data from a dump into the caller's company (which must be
    empty). Records a restore in the backup log.
    """

    permission_classes = [IsAuthenticated, RoleModuleAccess]
    rbac_module = "settings"

    def post(self, request):
        from org.models import Company
        company_id = getattr(request.user, "company_id", None)
        if company_id is None:
            return Response(
                {"detail": "A company-scoped user is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        dump = request.data.get("data")
        storage_key = request.data.get("storage_key")
        backup_id = request.data.get("backup_id")
        # Restore either from an inline dump or from one of the caller's own
        # stored backups (by record id, or the legacy object-storage key).
        # The record is resolved through the caller's company, never as an
        # arbitrary id/key: keys are predictable, and an unchecked lookup
        # would let one tenant restore another tenant's customers, suppliers
        # and cost prices into its own company.
        if not isinstance(dump, dict) and (backup_id or storage_key):
            lookup = {"pk": backup_id} if backup_id else {"storage_key": storage_key}
            record = BackupRecord.objects.filter(company_id=company_id, **lookup).first()
            if record is None or not record.is_downloadable:
                return Response(
                    {"detail": "That backup does not belong to your company."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            payload = snapshots.read(record)
            if not payload:
                return Response(
                    {"detail": "Could not read that backup from storage."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                dump = json.loads(payload)
            except (ValueError, TypeError):
                return Response(
                    {"detail": "Stored backup payload is not valid JSON."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        if not isinstance(dump, dict):
            return Response(
                {"detail": "data (a backup dump object) or backup_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # An inline dump is data the caller already holds (they downloaded it
        # from their own backup), so restoring it into a fresh company after a
        # re-creation is legitimate; only the by-key path needs the ownership
        # check above, because that path fetches data the caller never had.
        company = Company.objects.get(pk=company_id)
        # mode=missing adds only what the company does not have (the everyday
        # case: something was deleted); dry_run answers what it would add
        # without writing, so the owner sees it before agreeing.
        mode = request.data.get("mode") or services.EMPTY_ONLY
        dry_run = str(request.data.get("dry_run", "")).lower() in ("1", "true", "yes")
        result = restore_master(company, dump, request.user, mode=mode, dry_run=dry_run)
        if dry_run:
            return Response(result, status=status.HTTP_200_OK)
        record = BackupRecord.objects.create(
            company=company, kind=BackupRecord.RESTORE, status=BackupRecord.SUCCESS,
            record_count=result["restored"],
            created_by=request.user if request.user.is_authenticated else None,
        )
        log_activity(
            action="create", request=request, entity_type="BackupRecord",
            entity_id=record.id,
            metadata={"kind": "restore", "mode": mode, **result},
        )
        return Response(result, status=status.HTTP_200_OK)


class BackupDownloadView(APIView):
    """GET /api/ops/backups/<id>/download/ — the snapshot as a JSON file.

    Resolved through the caller's own company, like restore; a record with
    no stored payload (pre-tier metadata-only rows) is a 404.
    """

    permission_classes = [IsAuthenticated, RoleModuleAccess]
    rbac_module = "settings"

    def get(self, request, pk):
        company_id = getattr(request.user, "company_id", None)
        record = BackupRecord.objects.filter(company_id=company_id, pk=pk).first()
        payload = snapshots.read(record) if record is not None else None
        if not payload:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        stamp = record.created_at.strftime("%Y-%m-%dT%H-%M-%S")
        response = HttpResponse(payload, content_type="application/json; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="vezano-backup-{stamp}-{record.kind}.json"'
        )
        response["Cache-Control"] = "no-store"
        return response


class PreferenceView(APIView):
    """Per-user language + theme. Personal, so authenticated (no module gate)."""

    permission_classes = [IsAuthenticated]

    def _serialize(self, pref):
        return {
            "language": pref.language,
            "theme": pref.theme,
            "direction": pref.direction,
        }

    def get(self, request):
        pref, _ = UserPreference.objects.get_or_create(
            user=request.user,
            defaults={"language": settings.LANGUAGE_CODE.split("-")[0]},
        )
        return Response(self._serialize(pref))

    def patch(self, request):
        pref, _ = UserPreference.objects.get_or_create(
            user=request.user,
            defaults={"language": settings.LANGUAGE_CODE.split("-")[0]},
        )
        language = request.data.get("language")
        theme = request.data.get("theme")
        if language is not None:
            if language not in dict(UserPreference.LANGUAGE_CHOICES):
                return Response(
                    {"detail": "Unsupported language."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            pref.language = language
        if theme is not None:
            if theme not in dict(UserPreference.THEME_CHOICES):
                return Response(
                    {"detail": "Unsupported theme."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            pref.theme = theme
        pref.save()
        return Response(self._serialize(pref))


class LanguagesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response([
            {"code": code, "name": name,
             "direction": "rtl" if code == "ar" else "ltr"}
            for code, name in settings.LANGUAGES
        ])
