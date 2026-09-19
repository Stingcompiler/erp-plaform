"""Send one bilingual test email through the configured SMTP server.

Django's ``sendtestemail`` proves the connection; this proves what a person
will actually receive — the Arabic block right-to-left, the English block
left-to-right, and the link as a button — so an operator can check the
rendering in a real inbox after changing EMAIL_* settings.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core import mailer


class Command(BaseCommand):
    help = "Send a bilingual (ar/en) test email to one address."

    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument(
            "--primary", choices=["ar", "en"], default="ar",
            help="Which language leads (default: ar).",
        )

    def handle(self, *args, **options):
        if not mailer.email_is_enabled():
            raise CommandError("EMAIL_HOST is not set; nothing can be sent.")
        stamp = timezone.now().strftime("%Y-%m-%d %H:%M %Z")
        sent = mailer.send_bilingual(
            subject_ar="رسالة تجريبية من فيزانو",
            subject_en="Vezano test email",
            ar=[
                "مرحباً،",
                f"هذه رسالة تجريبية أُرسلت في {stamp} للتأكد من إعدادات البريد.",
                "إن وصلتك بشكل صحيح فالإعداد يعمل.",
            ],
            en=[
                "Hello,",
                f"This is a test message sent at {stamp} to verify the email settings.",
                "If it reached you, the configuration works.",
            ],
            link=(getattr(settings, "PUBLIC_APP_ORIGIN", "") or None),
            recipient=options["email"],
            primary=options["primary"],
        )
        if not sent:
            raise CommandError("The SMTP server refused the message; see the log above.")
        self.stdout.write(self.style.SUCCESS(f"Sent to {options['email']} via {settings.EMAIL_HOST}"))
