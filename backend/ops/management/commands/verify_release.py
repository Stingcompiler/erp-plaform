import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from ops import release


class Command(BaseCommand):
    """
    Verify this tree against its release manifest.

    The release pipeline signs the manifest; the customer server checks it here
    before an upgrade touches the database. A non-zero exit means the tree does
    not match what the vendor built, and the upgrade must not proceed.
    """

    help = "Check this installation against release-manifest.json."

    def add_arguments(self, parser):
        parser.add_argument(
            "--manifest",
            default="",
            help="Path to the manifest (default: <repository root>/release-manifest.json).",
        )

    def handle(self, *args, **options):
        root = release.repository_root()
        manifest_path = (
            Path(options["manifest"])
            if options["manifest"]
            else root / release.MANIFEST_NAME
        )
        if not manifest_path.is_file():
            raise CommandError(f"No manifest found at {manifest_path}.")

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            raise CommandError(f"Could not read the manifest: {exc}") from exc

        problems = release.verify_manifest(manifest, root=root)
        if problems:
            self.stderr.write(self.style.ERROR("Release verification FAILED:"))
            for problem in problems:
                self.stderr.write(f"  - {problem}")
            raise CommandError(
                f"{len(problems)} problem(s) found; do not upgrade with this tree."
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Release {manifest.get('application_version', 'unknown')} verified: "
                f"{len(manifest.get('migrations') or [])} migration(s), "
                f"frontend hash matches."
            )
        )
