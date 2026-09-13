from django.core.management.base import BaseCommand, CommandError

from config.deployment import get_deployment_config
from licensing.models import Installation


class Command(BaseCommand):
    help = "Create or show the stable identity of a standalone Vezano installation."

    def add_arguments(self, parser):
        parser.add_argument("--organisation", required=True)
        parser.add_argument("--app-version", default="")

    def handle(self, *args, **options):
        if not get_deployment_config().is_standalone:
            raise CommandError(
                "Set VEZANO_DEPLOYMENT_MODE=standalone before bootstrapping."
            )
        installation = Installation.current()
        changed = []
        for field, value in (
            ("organisation_name", options["organisation"]),
            ("application_version", options["app_version"]),
        ):
            if value and getattr(installation, field) != value:
                setattr(installation, field, value)
                changed.append(field)
        if changed:
            installation.save(update_fields=changed + ["updated_at"])
        self.stdout.write(
            self.style.SUCCESS(
                f"Standalone installation ID: {installation.installation_id}"
            )
        )
