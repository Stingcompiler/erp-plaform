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

    def test_signed_with_the_product_name(self):
        self._send()
        message = mail.outbox[0]
        self.assertIn("— Vezano Pro · فيزانو برو", message.body)
        html = message.alternatives[0][0]
        self.assertIn("فيزانو برو — إدارة متكاملة لشركتك وفروعها", html)
        self.assertIn("Vezano Pro — integrated management for companies and branches", html)
        self.assertIn('href="https://vezano.app"', html)

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


@override_settings(
    EMAIL_ENABLED=True,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    PUBLIC_APP_ORIGIN="https://app.example.test/",
)
class BilingualTemplateTests(SimpleTestCase):
    """The branded layout (templates/emails/bilingual.html)."""

    LINK = "https://vezano.app/activate-owner/?token=abc&kind=owner"

    def _html(self, **overrides):
        kwargs = dict(
            subject_ar="عنوان", subject_en="Subject",
            ar=["مرحباً سارة،", "سطر عربي ثانٍ"], en=["Hello Sara,", "Second English line"],
            link=self.LINK, recipient="to@example.com", primary="ar",
        )
        kwargs.update(overrides)
        self.assertTrue(mailer.send_bilingual(**kwargs))
        message = mail.outbox[-1]
        html, mimetype = message.alternatives[0]
        self.assertEqual(mimetype, "text/html")
        return message, html

    def test_primary_block_first_with_its_direction(self):
        _, html = self._html(primary="ar")
        self.assertIn('<html lang="ar" dir="rtl"', html)
        arabic = html.index('dir="rtl" lang="ar" align="right"')
        english = html.index('dir="ltr" lang="en" align="left"')
        self.assertLess(arabic, english)
        self.assertLess(html.index("سطر عربي ثانٍ"), html.index("Second English line"))

        _, html = self._html(primary="en")
        self.assertIn('<html lang="en" dir="ltr"', html)
        self.assertLess(
            html.index('dir="ltr" lang="en" align="left"'),
            html.index('dir="rtl" lang="ar" align="right"'),
        )
        self.assertLess(html.index("Second English line"), html.index("سطر عربي ثانٍ"))

    def test_button_and_raw_link_only_with_a_link(self):
        _, html = self._html()
        escaped = "https://vezano.app/activate-owner/?token=abc&amp;kind=owner"
        self.assertEqual(html.count(f'href="{escaped}"'), 2)  # button + raw link
        self.assertIn('class="vz-btn"', html)
        self.assertIn("فتح الرابط", html)
        self.assertIn("Open the link", html)

        _, html = self._html(link=None)
        self.assertNotIn('class="vz-btn"', html)
        self.assertNotIn("activate-owner", html)
        self.assertNotIn("فتح الرابط", html)

    def test_custom_button_labels(self):
        _, html = self._html(button_label_ar="تفعيل الحساب", button_label_en="Activate")
        self.assertIn("تفعيل الحساب", html)
        self.assertIn(">Activate</span>", html)
        self.assertNotIn("Open the link", html)

    def test_user_text_is_escaped(self):
        _, html = self._html(
            ar=['<script>alert("x")</script>'], en=['<img src=x onerror="y">'],
        )
        self.assertNotIn("<script>alert", html)
        self.assertIn("&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;", html)
        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;img src=x onerror=&quot;y&quot;&gt;", html)

    def test_logo_is_an_absolute_png_from_the_public_origin(self):
        _, html = self._html(primary="ar")
        self.assertIn('src="https://app.example.test/email/logo-ar.png"', html)
        self.assertIn('width="240" height="60" alt="فيزانو برو"', html)
        _, html = self._html(primary="en")
        self.assertIn('src="https://app.example.test/email/logo-en.png"', html)
        self.assertIn('alt="Vezano Pro"', html)

    @override_settings(PUBLIC_APP_ORIGIN="")
    def test_logo_falls_back_to_the_canonical_host(self):
        _, html = self._html()
        self.assertIn('src="https://vezano.app/email/logo-ar.png"', html)

    def test_preheader_defaults_to_the_first_primary_line(self):
        _, html = self._html(primary="en")
        preheader = html.index("mso-hide:all")
        self.assertEqual(html.index("Hello Sara,", preheader), html.index("Hello Sara,"))
        self.assertLess(html.index("Hello Sara,") - preheader, 200)
        _, html = self._html(preheader="Your account is ready")
        self.assertIn("Your account is ready&#8204;", html)

    def test_email_client_essentials(self):
        _, html = self._html()
        self.assertIn('<meta name="color-scheme" content="light dark">', html)
        self.assertIn("max-width:600px", html)
        self.assertIn("@media only screen and (max-width: 480px)", html)
        self.assertIn("@media (prefers-color-scheme: dark)", html)
        self.assertNotIn("<svg", html)
        self.assertIn("<title>عنوان | Subject</title>", html)

    def test_plain_text_twin_is_kept(self):
        message, _ = self._html(primary="en")
        self.assertEqual(
            message.body,
            "Hello Sara,\nSecond English line\n\n" + self.LINK
            + "\n\nمرحباً سارة،\nسطر عربي ثانٍ\n\n— Vezano Pro · فيزانو برو",
        )

    def test_signature_is_backward_compatible(self):
        import inspect

        params = inspect.signature(mailer.send_bilingual).parameters
        self.assertEqual(
            list(params)[:7],
            ["subject_ar", "subject_en", "ar", "en", "recipient", "link", "primary"],
        )
        for name, param in params.items():
            self.assertEqual(param.kind, param.KEYWORD_ONLY, name)
            if name not in ("subject_ar", "subject_en", "ar", "en", "recipient"):
                self.assertIsNone(param.default, name)

    def test_logo_files_exist_at_2x(self):
        import struct
        from pathlib import Path

        public = Path(__file__).resolve().parents[2] / "frontend" / "public" / "email"
        for code in ("ar", "en"):
            data = (public / f"logo-{code}.png").read_bytes()
            self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
            width, height = struct.unpack(">II", data[16:24])
            self.assertEqual(
                (width, height), (mailer.LOGO_WIDTH * 2, mailer.LOGO_HEIGHT * 2), code
            )
