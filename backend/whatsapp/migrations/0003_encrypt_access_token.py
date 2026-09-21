"""Seal the WhatsApp permanent token at rest (F15).

The plaintext column is renamed to ``access_token_encrypted`` and every
non-empty value is encrypted in place under the configured key.
"""
from django.db import migrations, models


def encrypt_tokens(apps, schema_editor):
    from core.secrets import encrypt, is_encrypted

    WhatsAppAccount = apps.get_model("whatsapp", "WhatsAppAccount")
    for account in WhatsAppAccount.objects.exclude(access_token_encrypted=""):
        if not is_encrypted(account.access_token_encrypted):
            account.access_token_encrypted = encrypt(account.access_token_encrypted)
            account.save(update_fields=["access_token_encrypted"])


class Migration(migrations.Migration):

    dependencies = [
        ("whatsapp", "0002_whatsapp_sending"),
    ]

    operations = [
        migrations.RenameField(
            model_name="whatsappaccount", old_name="access_token", new_name="access_token_encrypted",
        ),
        migrations.AlterField(
            model_name="whatsappaccount",
            name="access_token_encrypted",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.RunPython(encrypt_tokens, migrations.RunPython.noop),
    ]
