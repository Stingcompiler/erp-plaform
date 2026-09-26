from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from ops.transfer import TransferError, import_company, read_export, verify_transfer
from org.models import Company


class Command(BaseCommand):
    help = "Import a Vezano Pro company archive into a newly created tenant."

    def add_arguments(self, parser):
        parser.add_argument("--archive", required=True)
        parser.add_argument("--name", default="")
        parser.add_argument("--slug", default="")
        parser.add_argument("--no-media", action="store_true")

    def handle(self, *args, **options):
        archive_path = Path(options["archive"])
        if not archive_path.is_file():
            raise CommandError(f"Archive does not exist: {archive_path}")

        archive = None
        try:
            payload, archive = read_export(archive_path)
            source = payload["source"]
            fields = dict(source.get("fields") or {})
            fields.pop("is_active", None)
            fields["name"] = options["name"] or fields.get("name") or source["name"]
            fields["slug"] = (
                options["slug"] or fields.get("slug") or source.get("slug", "")
            )
            fields["currency"] = fields.get("currency") or source.get("currency", "SDG")
            if fields["slug"] and Company.objects.filter(slug=fields["slug"]).exists():
                raise TransferError(
                    f"Company slug '{fields['slug']}' already exists; pass --slug with a new value."
                )

            with transaction.atomic():
                company = Company.objects.create(**fields)
                report = import_company(
                    payload,
                    company,
                    archive=archive if not options["no_media"] else None,
                )
                differences = verify_transfer(payload, company)
                if differences:
                    raise TransferError(
                        "Transfer verification failed: " + "; ".join(differences)
                    )
        except (KeyError, OSError, TransferError, TypeError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        finally:
            if archive is not None:
                archive.close()

        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {report.total_created} row(s) into company #{company.pk} "
                f"({company.name}). User passwords were disabled and must be reset."
            )
        )
