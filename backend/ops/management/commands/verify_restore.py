import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from ops import restore_check


class Command(BaseCommand):
    """
    Compare the live database against a fingerprint captured at backup time.

    Run this on the restored database (ideally an isolated one) before pointing
    users at it. A non-zero exit means the restore did not reproduce every table,
    and the instance must not go live.
    """

    help = "Verify a restored database against a backup fingerprint."

    def add_arguments(self, parser):
        parser.add_argument(
            "--expected",
            required=True,
            help="Path to the fingerprint JSON written by backup_snapshot.",
        )

    def handle(self, *args, **options):
        expected_path = Path(options["expected"])
        if not expected_path.is_file():
            raise CommandError(f"No fingerprint found at {expected_path}.")
        try:
            expected = json.loads(expected_path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            raise CommandError(f"Could not read the fingerprint: {exc}") from exc

        actual = restore_check.data_fingerprint(
            company_id=expected.get("company_id"),
            include_media="media" in expected,
            with_media_hash=bool((expected.get("media") or {}).get("sha256")),
        )
        problems = restore_check.compare_fingerprints(expected, actual)

        if problems:
            self.stderr.write(self.style.ERROR("Restore verification FAILED:"))
            for problem in problems:
                self.stderr.write(f"  - {problem}")
            raise CommandError(
                f"{len(problems)} difference(s) found; do not point users at this database."
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Restore verified: {len(actual['counts'])} table(s) and media totals match "
                f"the backup of version {expected.get('application_version', 'unknown')}."
            )
        )
