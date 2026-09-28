"""Review F15: a request authenticated by the auth *cookie* must carry the
CSRF token; one authenticated by an Authorization header need not (a header
is never attached by the browser on its own). Public endpoints authenticate
nobody, so they stay as they are."""

from django.conf import settings
from django.core.cache import cache
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from accounts.models import Role, User
from org.models import Company

CSRF_COOKIE = settings.CSRF_COOKIE_NAME


class CookieCsrfTests(APITestCase):
    """Every client here enforces CSRF, as a browser would."""

    def setUp(self):
        cache.clear()
        self.company = Company.objects.create(name="Alpha")
        role = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        User.objects.create_user(
            email="owner@alpha.test", password="Owner-passw0rd!x",
            company=self.company, role=role, full_name="Owner",
        )

    def _browser(self):
        client = APIClient(enforce_csrf_checks=True)
        response = client.post(
            reverse("auth-login"),
            {"email": "owner@alpha.test", "password": "Owner-passw0rd!x", "device_id": "TILL1"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        return client, response

    def test_login_and_identity_issue_the_csrf_cookie(self):
        client, response = self._browser()
        self.assertIn(CSRF_COOKIE, response.cookies)
        self.assertFalse(response.cookies[CSRF_COOKIE]["httponly"])
        # A browser that lost the cookie gets it back from the identity call.
        del client.cookies[CSRF_COOKIE]
        me = client.get(reverse("auth-me"))
        self.assertEqual(me.status_code, 200)
        self.assertIn(CSRF_COOKIE, me.cookies)

    def test_cookie_authenticated_post_without_token_is_refused(self):
        client, _ = self._browser()
        response = client.post(reverse("attention-seen"), {"key": "x"}, format="json")
        self.assertEqual(response.status_code, 403, response.data)
        self.assertEqual(response.data["code"], "csrf_failed")
        # Reads are not affected.
        self.assertEqual(client.get(reverse("auth-me")).status_code, 200)

    def test_cookie_authenticated_post_with_the_header_passes(self):
        client, _ = self._browser()
        token = client.cookies[CSRF_COOKIE].value
        response = client.post(
            reverse("attention-seen"), {"key": "x"}, format="json", HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 200, response.data)
        # A token that does not match the cookie is as good as none.
        wrong = client.post(
            reverse("attention-seen"), {"key": "x"}, format="json", HTTP_X_CSRFTOKEN="nope",
        )
        self.assertEqual(wrong.status_code, 403)

    def test_cross_site_origin_is_refused_even_with_a_token(self):
        client, _ = self._browser()
        token = client.cookies[CSRF_COOKIE].value
        response = client.post(
            reverse("attention-seen"), {"key": "x"}, format="json",
            HTTP_X_CSRFTOKEN=token, HTTP_ORIGIN="https://evil.example",
        )
        self.assertEqual(response.status_code, 403)

    def test_bearer_header_needs_no_token(self):
        browser, login = self._browser()
        access = login.cookies[settings.SIMPLE_JWT["AUTH_COOKIE"]].value
        script = APIClient(enforce_csrf_checks=True, HTTP_AUTHORIZATION=f"Bearer {access}")
        self.assertEqual(script.get(reverse("auth-me")).status_code, 200)
        response = script.post(reverse("attention-seen"), {"key": "x"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)

    def test_public_endpoints_are_unaffected(self):
        """Unauthenticated endpoints authenticate nobody, so a signed-in
        browser without the header and an anonymous visitor both pass."""
        client, _ = self._browser()
        for who in (client, APIClient(enforce_csrf_checks=True)):
            response = who.post(reverse("platform-track"), {"q": "nothing"}, format="json")
            self.assertNotEqual(response.status_code, 403, response.data)
            plans = who.get(reverse("public-plan-list"))
            self.assertEqual(plans.status_code, 200)
