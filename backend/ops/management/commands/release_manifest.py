from django.core.management.base import BaseCommand

from ops import release


class Command(BaseCommand):
    """
    Build the release manifest for this tree and write it beside SHA256SUMS.

    Run this in the release pipeline *after* `npm run build` in frontend/, so the
    manifest captures the frontend export that ships with the release. The
    manifest is what `verify_release` and `preflight` compare against on the
    customer's server.
    """

    help = "Write release-manifest.json and SHA256SUMS for this build."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-dir",
            default="",
            help="Directory to write the manifest into (default: repository root).",
        )
        parser.add_argument(
            "--note",
            default="",
            help="Optional free-text note recorded in the manifest.",
        )

    def handle(self, *args, **options):
        root = release.repository_root()
        destination = options["output_dir"]
        if destination:
            from pathlib import Path

            out_dir = Path(destination).resolve()
        else:
            out_dir = root

        extra = {"release_note": options["note"]} if options["note"] else None
        manifest = release.build_manifest(root=root, extra=extra)

        if not (manifest.get("frontend") or {}).get("present"):
            self.stderr.write(
                self.style.WARNING(
                    "The frontend export is missing — run `npm run build` in "
                    "frontend/ before packaging a release."
                )
            )

        manifest_path = release.write_manifest(
            manifest, out_dir / release.MANIFEST_NAME
        )
        checksums_path = release.write_checksums(
            manifest, out_dir / release.CHECKSUM_NAME, root=root
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Version {manifest['application_version']}: "
                f"{len(manifest['migrations'])} migration(s), "
                f"{len(manifest['dependencies']['packages'])} dependency line(s), "
                "frontend "
                f"{'present' if (manifest.get('frontend') or {}).get('present') else 'MISSING'}."
            )
        )
        self.stdout.write(f"Manifest:  {manifest_path}")
        self.stdout.write(f"Checksums: {checksums_path}")
