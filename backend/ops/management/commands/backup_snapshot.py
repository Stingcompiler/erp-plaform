import json
from pathlib import Path

from django.core.management.base import BaseCommand

from ops import restore_check


class Command(BaseCommand):
    """
    Write a data fingerprint for the current database (and media).

    `backup.sh` calls this right before `pg_dump` so the backup directory carries
    the exact counts it captured. After a restore it is compared against the live
    database with `verify_restore`.
    """

    help = "Write a row-count and media fingerprint beside a backup."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            required=True,
            help="Path to write the fingerprint JSON to.",
        )
        parser.add_argument(
            "--company",
            type=int,
            default=None,
            help="Restrict counts to one company (default: the whole installation).",
        )
        parser.add_argument(
            "--media-hash",
            action="store_true",
            help="Include the media tree hash (slower on large media trees).",
        )
        parser.add_argument(
            "--no-media",
            action="store_true",
            help="Skip media entirely (database-only fingerprint).",
        )

    def handle(self, *args, **options):
        fingerprint = restore_check.data_fingerprint(
            company_id=options["company"],
            include_media=not options["no_media"],
            with_media_hash=options["media_hash"],
        )
        destination = Path(options["output"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(fingerprint, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        counted = len(fingerprint["counts"])
        self.stdout.write(
            self.style.SUCCESS(f"Fingerprint written: {counted} table(s) → {destination}")
        )
