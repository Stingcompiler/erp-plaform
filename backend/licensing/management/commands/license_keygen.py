"""Create the vendor's licence signing key pair — run once, on the vendor's machine."""

import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from licensing.issuing import generate_keypair


class Command(BaseCommand):
    help = (
        "Generate an Ed25519 signing key pair for issuing standalone licences. "
        "The private key stays with the vendor; the public key is shipped to "
        "installations in VEZANO_LICENSE_PUBLIC_KEYS."
    )

    def add_arguments(self, parser):
        parser.add_argument("--key-id", required=True, help='e.g. "vezano-2026"')
        parser.add_argument(
            "--out-dir",
            required=True,
            help="Directory OUTSIDE the repository to write <key-id>.private.pem / .public.pem",
        )

    def handle(self, *args, **options):
        out = Path(options["out_dir"]).expanduser().resolve()
        repo_root = Path(__file__).resolve().parents[4]
        if repo_root in out.parents or out == repo_root:
            raise CommandError("Refusing to write a private key inside the repository.")
        out.mkdir(parents=True, exist_ok=True)
        key_id = options["key_id"]
        private_path = out / f"{key_id}.private.pem"
        public_path = out / f"{key_id}.public.pem"
        if private_path.exists():
            raise CommandError(f"{private_path} already exists; will not overwrite a signing key.")
        private_pem, public_pem = generate_keypair()
        private_path.write_text(private_pem, encoding="utf-8")
        os.chmod(private_path, 0o600)
        public_path.write_text(public_pem, encoding="utf-8")
        self.stdout.write(
            self.style.SUCCESS(
                f"Private key: {private_path} (mode 600 — back it up, never commit it)"
            )
        )
        self.stdout.write(self.style.SUCCESS(f"Public key:  {public_path}"))
        self.stdout.write("")
        self.stdout.write(
            f"Ship {public_path.name} to every customer: copy it into the directory "
            "named by VEZANO_LICENSE_PUBLIC_KEYS_DIR in their vezano.env "
            "(the runbook uses /etc/vezano/license-keys). Adding a rotated key is "
            "another file copy; existing licences keep verifying."
        )
        self.stdout.write("")
        self.stdout.write(
            "Alternative for environments without a file drop (no spaces — shells "
            "split on them):"
        )
        import json

        self.stdout.write(
            "VEZANO_LICENSE_PUBLIC_KEYS="
            + json.dumps({key_id: public_pem}, ensure_ascii=False, separators=(",", ":"))
        )
