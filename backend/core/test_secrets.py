"""Credentials held for tenants are sealed at rest (F15)."""
from cryptography.fernet import Fernet
from django.db import connection
from django.test import TestCase, override_settings

from core import secrets
from whatsapp.models import WhatsAppAccount


class SecretsTests(TestCase):
    def test_round_trip_and_prefix(self):
        stored = secrets.encrypt("EAAB-secret")
        self.assertTrue(stored.startswith(secrets.PREFIX))
        self.assertNotIn("EAAB-secret", stored)
        self.assertEqual(secrets.decrypt(stored), "EAAB-secret")
        self.assertEqual(secrets.encrypt(""), "")
        self.assertEqual(secrets.decrypt(""), "")

    def test_legacy_plaintext_is_returned_as_is(self):
        self.assertEqual(secrets.decrypt("plain-old-token"), "plain-old-token")

    def test_rotation_reads_the_previous_key_and_rewrites_under_the_current(self):
        old_key = Fernet.generate_key().decode()
        new_key = Fernet.generate_key().decode()
        with override_settings(SECRETS_ENCRYPTION_KEY=old_key):
            stored = secrets.encrypt("tok")
        with override_settings(
            SECRETS_ENCRYPTION_KEY=new_key, SECRETS_ENCRYPTION_KEY_PREVIOUS=old_key
        ):
            self.assertEqual(secrets.decrypt(stored), "tok")
            rotated = secrets.rotate(stored)
        # Without the previous key the old ciphertext is unreadable, the
        # rotated one still works: rotation actually re-encrypted.
        with override_settings(SECRETS_ENCRYPTION_KEY=new_key):
            self.assertEqual(secrets.decrypt(rotated), "tok")
            with self.assertRaises(secrets.SecretUnreadable):
                secrets.decrypt(stored)

    def test_whatsapp_token_is_ciphertext_in_the_database(self):
        account = WhatsAppAccount.objects.create(phone_number_id="PN-1")
        account.access_token = "EAAB-permanent"
        account.save()
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT access_token_encrypted FROM whatsapp_whatsappaccount WHERE id = %s",
                [account.pk],
            )
            raw = cursor.fetchone()[0]
        self.assertTrue(raw.startswith(secrets.PREFIX))
        self.assertNotIn("EAAB-permanent", raw)
        self.assertEqual(WhatsAppAccount.objects.get(pk=account.pk).access_token, "EAAB-permanent")
        self.assertTrue(account.has_token)

    def test_plaintext_written_around_the_property_is_sealed_on_save(self):
        # A legacy row (pre-migration value) or a raw update: the next save
        # encrypts it and reading still yields the token.
        account = WhatsAppAccount.objects.create(phone_number_id="PN-2")
        WhatsAppAccount.objects.filter(pk=account.pk).update(access_token_encrypted="legacy")
        account = WhatsAppAccount.objects.get(pk=account.pk)
        self.assertEqual(account.access_token, "legacy")
        account.save()
        self.assertTrue(secrets.is_encrypted(account.access_token_encrypted))
        self.assertEqual(WhatsAppAccount.objects.get(pk=account.pk).access_token, "legacy")


class RotateSecretsCommandTests(TestCase):
    def test_command_reseals_rows_and_reports_unreadable_ones(self):
        from io import StringIO

        from django.core.management import call_command

        old_key = Fernet.generate_key().decode()
        new_key = Fernet.generate_key().decode()
        with override_settings(SECRETS_ENCRYPTION_KEY=old_key):
            old_stored = secrets.encrypt("tok-old")
        with override_settings(SECRETS_ENCRYPTION_KEY=Fernet.generate_key().decode()):
            orphan = secrets.encrypt("tok-orphan")
        a = WhatsAppAccount.objects.create(phone_number_id="A", access_token_encrypted=old_stored)
        b = WhatsAppAccount.objects.create(phone_number_id="B", access_token_encrypted=orphan)
        out, err = StringIO(), StringIO()
        with override_settings(
            SECRETS_ENCRYPTION_KEY=new_key, SECRETS_ENCRYPTION_KEY_PREVIOUS=old_key
        ):
            call_command("rotate_secrets", stdout=out, stderr=err)
        self.assertIn("Rotated 1 secret(s); 1 unreadable.", out.getvalue())
        self.assertIn("UNREADABLE WhatsApp account B", err.getvalue())
        a.refresh_from_db()
        b.refresh_from_db()
        with override_settings(SECRETS_ENCRYPTION_KEY=new_key):
            self.assertEqual(a.access_token, "tok-old")
        self.assertEqual(b.access_token_encrypted, orphan)
