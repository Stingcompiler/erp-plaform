from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """Re-seal every stored credential under the current SECRETS_ENCRYPTION_KEY.

    Run after a key rotation, with the old key still in
    SECRETS_ENCRYPTION_KEY_PREVIOUS; once it reports zero unreadable rows
    the previous key can be dropped from the environment.
    """

    help = "Re-encrypt stored credentials under the current SECRETS_ENCRYPTION_KEY."

    def handle(self, *args, **options):
        from core.secrets import SecretUnreadable, rotate
        from whatsapp.models import WhatsAppAccount

        rotated = unreadable = 0
        for account in WhatsAppAccount.objects.exclude(access_token_encrypted=""):
            try:
                account.access_token_encrypted = rotate(account.access_token_encrypted)
            except SecretUnreadable:
                unreadable += 1
                self.stderr.write(
                    f"UNREADABLE WhatsApp account {account.phone_number_id}: "
                    "not encrypted under the current or previous key."
                )
                continue
            account.save(update_fields=["access_token_encrypted"])
            rotated += 1
        self.stdout.write(f"Rotated {rotated} secret(s); {unreadable} unreadable.")
