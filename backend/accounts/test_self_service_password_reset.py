"""Self-service password reset: no account enumeration, single-use link,
old sessions ended."""

from django.core import mail
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import Role, User
from org.models import Company

EMAIL = {
    "EMAIL_ENABLED": True,
    "EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend",
    "PUBLIC_APP_ORIGIN": "https://vezano.test",
}


@override_settings(**EMAIL)
class PasswordResetTests(TestCase):
    def setUp(self):
        company = Company.objects.create(name="Alpha")
        role = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        self.user = User.objects.create_user(
            email="owner@alpha.test", password="Old-passw0rd!x", company=company, role=role,
            full_name="Owner",
        )
        self.client = APIClient()

    def _request(self, email):
        return self.client.post("/api/auth/password-reset/", {"email": email}, format="json")

    def _link_parts(self):
        body = mail.outbox[-1].body
        url = next(part for part in body.split() if "/reset-password/?" in part)
        query = url.split("?", 1)[1]
        return dict(pair.split("=") for pair in query.split("&"))

    def test_known_and_unknown_addresses_get_the_same_answer(self):
        known = self._request("owner@alpha.test")
        unknown = self._request("nobody@alpha.test")
        self.assertEqual(known.status_code, 200)
        self.assertEqual(known.data, unknown.data)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/reset-password/?uid=", mail.outbox[0].body)

    def test_link_sets_a_new_password_once_and_ends_old_sessions(self):
        login = self.client.post(
            "/api/auth/login/", {"email": "owner@alpha.test", "password": "Old-passw0rd!x"},
            format="json",
        )
        self.assertEqual(login.status_code, 200)
        self._request("owner@alpha.test")
        parts = self._link_parts()
        confirm = self.client.post(
            "/api/auth/password-reset/confirm/",
            {**parts, "password": "Brand-new-passw0rd"}, format="json",
        )
        self.assertEqual(confirm.status_code, 200, confirm.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Brand-new-passw0rd"))
        # The refresh token from before the reset is dead.
        refresh = self.client.post("/api/auth/refresh/", {}, format="json")
        self.assertEqual(refresh.status_code, 401)
        # The link is single-use.
        again = self.client.post(
            "/api/auth/password-reset/confirm/",
            {**parts, "password": "Another-passw0rd!"}, format="json",
        )
        self.assertEqual(again.status_code, 400)

    def test_weak_password_is_refused(self):
        self._request("owner@alpha.test")
        parts = self._link_parts()
        response = self.client.post(
            "/api/auth/password-reset/confirm/", {**parts, "password": "short"}, format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("password", response.data)

    @override_settings(EMAIL_ENABLED=False)
    def test_reports_when_this_server_cannot_email(self):
        response = self._request("owner@alpha.test")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["email_enabled"])
        self.assertEqual(len(mail.outbox), 0)
