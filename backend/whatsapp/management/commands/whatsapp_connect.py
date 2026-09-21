"""Connect (or update) a WhatsApp Business number.

    python manage.py whatsapp_connect --phone-number-id 1234567890 \\
        --display-phone 249912345678 --company "تجار الجملة" [--waba-id …] \\
        [--token-env WHATSAPP_TOKEN_SHOP1] [--name "متجر …"]

The access token is read from the named environment variable, never from
the command line, so it does not land in shell history. Omit --company
for the platform's own number. Until P1 ships a settings screen, this is
how an operator links a number from the Render shell.
"""
import os

from django.core.management.base import BaseCommand, CommandError

from org.models import Company
from whatsapp.models import WhatsAppAccount, digits_only


class Command(BaseCommand):
    help = "Connect a WhatsApp Business phone number to a company (or the platform)."

    def add_arguments(self, parser):
        parser.add_argument("--phone-number-id", required=True)
        parser.add_argument("--display-phone", default="")
        parser.add_argument("--company", default="", help="Company name; empty = platform number.")
        parser.add_argument("--waba-id", default="")
        parser.add_argument("--name", default="")
        parser.add_argument(
            "--token-env", default="",
            help="Environment variable holding the permanent access token.",
        )
        parser.add_argument("--deactivate", action="store_true")

    def handle(self, *args, **options):
        company = None
        if options["company"]:
            company = Company.objects.filter(name=options["company"]).first()
            if company is None:
                raise CommandError(f"No company named {options['company']!r}.")
        token = ""
        if options["token_env"]:
            token = os.environ.get(options["token_env"], "")
            if not token:
                raise CommandError(f"{options['token_env']} is empty or unset.")
        account, created = WhatsAppAccount.objects.get_or_create(
            phone_number_id=options["phone_number_id"].strip(),
            defaults={"company": company},
        )
        account.company = company
        if options["display_phone"]:
            account.display_phone = digits_only(options["display_phone"])
        if options["waba_id"]:
            account.waba_id = options["waba_id"].strip()
        if options["name"]:
            account.display_name = options["name"].strip()
        if token:
            account.access_token = token
        account.is_active = not options["deactivate"]
        account.save()
        owner = company.name if company else "platform"
        self.stdout.write(
            f"{'Connected' if created else 'Updated'} {account.phone_number_id} "
            f"({account.display_phone or 'no display phone'}) → {owner}; "
            f"token {'set' if account.has_token else 'not set'}; "
            f"{'active' if account.is_active else 'inactive'}."
        )
