"""Issue a signed standalone licence for one installation — vendor side."""

import json
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from licensing.issuing import build_payload, envelope_json, load_private_key, sign_payload


def _date(value):
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise CommandError(f"Dates must be YYYY-MM-DD: {value!r}") from exc


class Command(BaseCommand):
    help = "Sign a licence file for a customer's standalone installation."

    def add_arguments(self, parser):
        parser.add_argument("--private-key", required=True, help="Path to <key-id>.private.pem")
        parser.add_argument("--key-id", required=True)
        parser.add_argument(
            "--installation-id",
            required=True,
            help="From `manage.py bootstrap_standalone` on the customer server",
        )
        parser.add_argument("--organisation", required=True)
        parser.add_argument("--kind", choices=("perpetual", "term"), default="perpetual")
        parser.add_argument("--usable-until", help="Term licences: last usable day (YYYY-MM-DD)")
        parser.add_argument(
            "--grace-days",
            type=int,
            default=14,
            help="Term licences: days of grace after usable-until (default 14)",
        )
        parser.add_argument(
            "--maintenance-until",
            help="Last day the customer may install new releases (YYYY-MM-DD)",
        )
        parser.add_argument(
            "--max-version",
            default="",
            help="Highest application version this licence runs (e.g. 1.4.99)",
        )
        parser.add_argument(
            "--modules", default="*", help='Comma-separated module list, or "*" for all (default)'
        )
        parser.add_argument(
            "--limit",
            action="append",
            default=[],
            metavar="RESOURCE=N",
            help="e.g. --limit users=25 --limit branches=3",
        )
        parser.add_argument("--out", help="Write the licence JSON here (default: stdout)")

    def handle(self, *args, **options):
        limits = {}
        for item in options["limit"]:
            if "=" not in item:
                raise CommandError(f"--limit expects RESOURCE=N, got {item!r}")
            name, value = item.split("=", 1)
            try:
                limits[name.strip()] = int(value)
            except ValueError as exc:
                raise CommandError(f"--limit {name}: N must be an integer") from exc
        modules = [m.strip() for m in options["modules"].split(",") if m.strip()]
        try:
            private_key = load_private_key(options["private_key"])
            payload = build_payload(
                installation_id=options["installation_id"],
                organisation_name=options["organisation"],
                kind=options["kind"],
                key_id=options["key_id"],
                modules=modules,
                limits=limits,
                usable_until=_date(options["usable_until"]) if options["usable_until"] else None,
                grace_days=options["grace_days"],
                maintenance_until=(
                    _date(options["maintenance_until"]) if options["maintenance_until"] else None
                ),
                max_application_version=options["max_version"],
            )
        except (OSError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        envelope = sign_payload(payload, private_key)
        text = envelope_json(envelope)
        if options["out"]:
            Path(options["out"]).write_text(text, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"Licence written to {options['out']}"))
            self.stdout.write(
                json.dumps({k: payload[k] for k in ("license_id", "kind", "organisation_name")})
            )
        else:
            self.stdout.write(text)
