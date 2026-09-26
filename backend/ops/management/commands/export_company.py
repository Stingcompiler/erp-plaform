from django.core.management.base import BaseCommand, CommandError

from ops.transfer import TransferError, write_export
from org.models import Company


class Command(BaseCommand):
    help = "Export one tenant and its media to a portable Vezano Pro archive."

    def add_arguments(self, parser):
        parser.add_argument("--company", type=int, required=True)
        parser.add_argument("--output", required=True)
        parser.add_argument("--no-media", action="store_true")

    def handle(self, *args, **options):
        try:
            company = Company.objects.get(pk=options["company"])
            result = write_export(
                company,
                options["output"],
                include_media=not options["no_media"],
            )
        except Company.DoesNotExist as exc:
            raise CommandError("The requested company does not exist.") from exc
        except (OSError, TransferError) as exc:
            raise CommandError(str(exc)) from exc

        if result["media_missing"]:
            self.stderr.write(
                self.style.WARNING(
                    f"{len(result['media_missing'])} referenced media file(s) were missing."
                )
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"Exported {result['total_rows']} row(s) from {company.name} "
                f"to {result['destination']}."
            )
        )
