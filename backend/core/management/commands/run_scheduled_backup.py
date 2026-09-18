from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """
    Entry point for the `erp-backup-cron` Render Cron Job (daily).

    Performs a real logical backup of every active company, writing a
    BackupRecord per company (Rule #8) with the snapshot stored through
    ops.snapshots: object storage when configured, otherwise gzip in the
    database row — never the ephemeral local disk. Then prunes in-database
    payloads past BACKUP_RETENTION_DAYS, keeping each company's newest.
    """

    help = "Run scheduled logical backups for all active companies."

    def handle(self, *args, **options):
        from ops import snapshots
        from ops.models import BackupRecord
        from ops.services import dump_company
        from org.models import Company

        companies = Company.objects.filter(is_active=True)
        done = 0
        for company in companies:
            try:
                snapshots.store(company, BackupRecord.SCHEDULED, dump_company(company))
                done += 1
            except Exception as exc:  # noqa: BLE001
                BackupRecord.objects.create(
                    company=company, kind=BackupRecord.SCHEDULED,
                    status=BackupRecord.FAILED, note=str(exc)[:255],
                )
        pruned = snapshots.prune()
        self.stdout.write(
            self.style.SUCCESS(
                f"Scheduled backup complete: {done} companies, {pruned} old snapshots pruned."
            )
        )
