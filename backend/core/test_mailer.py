"""Email is a best-effort side channel: sent when configured, silent when
not, and never a reason for the calling flow to fail.

The provisioning and invitation tests use Django's locmem backend to assert
that a real SMTP configuration would have delivered the activation link to
the right inbox, and that the API keeps returning the token to the operator
either way.
"""

from unittest import mock

from django.core import mail
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from core import mailer


@override_settings(
    EMAIL_ENABLED=True, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"
)
class MailerTests(SimpleTestCase):
    def test_sends_when_enabled(self):
        self.assertTrue(mailer.send_transactional("Subject", "Body", "to@example.com"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["to@example.com"])

    @override_settings(EMAIL_ENABLED=False)
    def test_disabled_email_reports_not_sent(self):
        self.assertFalse(mailer.send_transactional("Subject", "Body", "to@example.com"))
        self.assertEqual(len(mail.outbox), 0)

    def test_smtp_failure_is_swallowed(self):
        with mock.patch("core.mailer.send_mail", side_effect=OSError("boom")):
            self.assertFalse(mailer.send_transactional("Subject", "Body", "to@example.com"))

    def test_no_recipient_means_no_send(self):
        self.assertFalse(mailer.send_transactional("Subject", "Body", ""))

    @override_settings(PUBLIC_APP_ORIGIN="https://vezano.app")
    def test_activation_link_shapes(self):
        self.assertEqual(
            mailer.activation_link("abc"), "https://vezano.app/activate-owner/?token=abc"
        )
        self.assertEqual(
            mailer.activation_link("abc", kind="platform"),
            "https://vezano.app/activate-owner/?kind=platform&token=abc",
        )

    @override_settings(PUBLIC_APP_ORIGIN="")
    def test_no_public_origin_means_no_link(self):
        self.assertIsNone(mailer.activation_link("abc"))


@override_settings(
    EMAIL_ENABLED=True,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    PUBLIC_APP_ORIGIN="https://vezano.app",
)
class PlatformInvitationEmailTests(TestCase):
    def setUp(self):
        from accounts.models import User

        self.admin = User.objects.create_superuser(
            email="root@vezano.test", password="Root-passw0rd!"
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_invite_emails_the_member_and_reports_it(self):
        response = self.client.post(
            "/api/platform/team/",
            {"email": "new@vezano.test", "full_name": "New Member", "role": "Support Agent"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data["invitation_email_sent"])
        self.assertIn("invitation_token", response.data)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["new@vezano.test"])
        self.assertIn("kind=platform", message.body)
        self.assertIn(response.data["invitation_token"], message.body)

    @override_settings(EMAIL_ENABLED=False)
    def test_invite_without_email_still_returns_the_token(self):
        response = self.client.post(
            "/api/platform/team/",
            {"email": "new2@vezano.test", "full_name": "New Member", "role": "Support Agent"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertFalse(response.data["invitation_email_sent"])
        self.assertIn("invitation_token", response.data)
        self.assertEqual(len(mail.outbox), 0)
