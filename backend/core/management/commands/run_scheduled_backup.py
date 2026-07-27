import json

from django.core.management.base import BaseCommand
from django.core.serializers.json import DjangoJSONEncoder


class Command(BaseCommand):
    """
    Entry point for the `erp-backup-cron` Render Cron Job (daily).

    M10: performs a real logical backup of every active company, writing a
    BackupRecord per company (Rule #8). The snapshot itself is generated in
    memory and its size/record-count recorded; wiring the payload to durable
    object storage (e.g. S3/R2) is an infra step noted in the milestone docs —
    Render's filesystem is ephemeral, so this command intentionally does not
    rely on local disk for retention.
    """

    help = "Run scheduled logical backups for all active companies."

    def handle(self, *args, **options):
        from ops.models import BackupRecord
        from ops.services import count_records, dump_company
        from ops.storage import upload_backup
        from org.models import Company

        companies = Company.objects.filter(is_active=True)
        done = 0
        for company in companies:
            try:
                data = dump_company(company)
                payload = json.dumps(data, cls=DjangoJSONEncoder)
                key = upload_backup(company.id, BackupRecord.SCHEDULED, payload)
                BackupRecord.objects.create(
                    company=company, kind=BackupRecord.SCHEDULED,
                    status=BackupRecord.SUCCESS,
                    record_count=count_records(data), size_bytes=len(payload),
                    storage_key=key or "",
                )
                done += 1
            except Exception as exc:  # noqa: BLE001
                BackupRecord.objects.create(
                    company=company, kind=BackupRecord.SCHEDULED,
                    status=BackupRecord.FAILED, note=str(exc)[:255],
                )
        self.stdout.write(
            self.style.SUCCESS(f"Scheduled backup complete: {done} companies.")
        )
