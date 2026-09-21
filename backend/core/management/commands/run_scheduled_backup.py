from django.core.management.base import BaseCommand, CommandError


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
        failed = []
        for company in companies:
            try:
                snapshots.store(company, BackupRecord.SCHEDULED, dump_company(company))
                done += 1
            except Exception as exc:  # noqa: BLE001
                BackupRecord.objects.create(
                    company=company, kind=BackupRecord.SCHEDULED,
                    status=BackupRecord.FAILED, note=str(exc)[:255],
                )
                failed.append(f"{company.name} (#{company.pk}): {exc}")
                self.stderr.write(f"FAILED {company.name} (#{company.pk}): {exc}")
        pruned = snapshots.prune()
        summary = f"{done} companies, {pruned} old snapshots pruned."
        # A cron that skipped a company must not look green: Render only
        # alerts on a non-zero exit, so every failure ends the run that way
        # after the other companies were still backed up.
        if failed:
            raise CommandError(
                f"Scheduled backup finished with {len(failed)} failure(s): {summary}\n"
                + "\n".join(failed)
            )
        self.stdout.write(self.style.SUCCESS(f"Scheduled backup complete: {summary}"))
