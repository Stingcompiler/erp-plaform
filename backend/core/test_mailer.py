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


@override_settings(
    EMAIL_ENABLED=True, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"
)
class BilingualEmailTests(SimpleTestCase):
    def _send(self, **overrides):
        kwargs = dict(
            subject_ar="عنوان", subject_en="Subject",
            ar=["مرحباً", "نص عربي"], en=["Hello", "English text"],
            link="https://vezano.app/reset-password/?uid=1&token=abc",
            recipient="to@example.com",
        )
        kwargs.update(overrides)
        return mailer.send_bilingual(**kwargs)

    def test_both_languages_in_text_and_html_with_directions(self):
        self.assertTrue(self._send())
        message = mail.outbox[0]
        self.assertIn("نص عربي", message.body)
        self.assertIn("English text", message.body)
        self.assertIn("https://vezano.app/reset-password/?uid=1&token=abc", message.body)
        html, mimetype = message.alternatives[0]
        self.assertEqual(mimetype, "text/html")
        self.assertIn('dir="rtl" lang="ar"', html)
        self.assertIn('dir="ltr" lang="en"', html)
        self.assertIn("uid=1&amp;token=abc", html)

    def test_screen_language_decides_the_order(self):
        from django.utils import translation

        with translation.override("en"):
            self._send()
        with translation.override("ar"):
            self._send()
        english_first, arabic_first = mail.outbox
        self.assertEqual(english_first.subject, "Subject | عنوان")
        self.assertLess(english_first.body.index("Hello"), english_first.body.index("مرحباً"))
        self.assertEqual(arabic_first.subject, "عنوان | Subject")
        self.assertLess(arabic_first.body.index("مرحباً"), arabic_first.body.index("Hello"))

    def test_explicit_primary_wins(self):
        self._send(primary="en")
        self.assertTrue(mail.outbox[0].subject.startswith("Subject"))

    @override_settings(EMAIL_ENABLED=False)
    def test_disabled_reports_not_sent(self):
        self.assertFalse(self._send())
        self.assertEqual(len(mail.outbox), 0)

    def test_html_escapes_names(self):
        self._send(ar=["<b>x</b>"], en=["<i>y</i>"])
        html = mail.outbox[0].alternatives[0][0]
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", html)
        self.assertNotIn("<b>x</b>", html)
