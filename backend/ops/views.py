import json

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.activity import log_activity
from core.rbac import RoleModuleAccess
from ops.models import BackupRecord, UserPreference
from ops.services import count_records, dump_company, restore_master


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
        records = BackupRecord.objects.filter(company_id=company_id).values(
            "id", "kind", "status", "record_count", "size_bytes",
            "storage_key", "created_at"
        )
        return Response(list(records))

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
        payload = json.dumps(data, cls=DjangoJSONEncoder)
        from ops import storage
        storage_key = storage.upload_backup(company_id, BackupRecord.MANUAL, payload)
        record = BackupRecord.objects.create(
            company=company, kind=BackupRecord.MANUAL, status=BackupRecord.SUCCESS,
            record_count=count_records(data), size_bytes=len(payload),
            storage_key=storage_key or "",
            created_by=request.user if request.user.is_authenticated else None,
        )
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
        # Restore either from an inline dump or by fetching a stored backup.
        if not isinstance(dump, dict) and storage_key:
            from ops import storage
            payload = storage.download_backup(storage_key)
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
                {"detail": "data (a backup dump object) or storage_key is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        company = Company.objects.get(pk=company_id)
        restored = restore_master(company, dump, request.user)
        record = BackupRecord.objects.create(
            company=company, kind=BackupRecord.RESTORE, status=BackupRecord.SUCCESS,
            record_count=restored,
            created_by=request.user if request.user.is_authenticated else None,
        )
        log_activity(
            action="create", request=request, entity_type="BackupRecord",
            entity_id=record.id, metadata={"kind": "restore", "restored": restored},
        )
        return Response({"restored": restored}, status=status.HTTP_200_OK)


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
        pref, _ = UserPreference.objects.get_or_create(user=request.user)
        return Response(self._serialize(pref))

    def patch(self, request):
        pref, _ = UserPreference.objects.get_or_create(user=request.user)
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
