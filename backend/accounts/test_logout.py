"""Signing out ends the session on a shared device, whatever the tokens say.

The access cookie lives 30 minutes. Sign-out used to require it, so a
cashier who signed out after it lapsed got a 401 and left the 7-day
refresh cookie alive: the next person on the tablet was signed straight
back in as them."""

from django.conf import settings
from django.urls import reverse
from rest_framework import status

from accounts.tests import ACCESS_COOKIE, REFRESH_COOKIE, BaseTenantSetup
from core.models import ActivityLog


class LogoutTests(BaseTenantSetup):
    def _cleared(self, response, name):
        cookie = response.cookies.get(name)
        return cookie is not None and cookie.value == "" and cookie["max-age"] == 0

    def test_sign_out_with_an_expired_access_cookie_kills_the_refresh_token(self):
        self.login("a@alpha.test")
        refresh = self.client.cookies[REFRESH_COOKIE].value
        # The access cookie lapsed (the browser dropped it).
        del self.client.cookies[ACCESS_COOKIE]
        response = self.client.post(reverse("auth-logout"))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        self.assertTrue(self._cleared(response, ACCESS_COOKIE))
        self.assertTrue(self._cleared(response, REFRESH_COOKIE))
        self.assertTrue(self._cleared(response, settings.CSRF_COOKIE_NAME))
        self.assertEqual(ActivityLog.objects.filter(action="logout", user=self.user_a).count(), 1)
        # The old refresh token cannot mint a new session.
        self.client.cookies.clear()
        self.client.cookies[REFRESH_COOKIE] = refresh
        again = self.client.post(reverse("auth-refresh"))
        self.assertEqual(again.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_sign_out_with_a_garbage_access_cookie_still_succeeds(self):
        self.login("a@alpha.test")
        self.client.cookies[ACCESS_COOKIE] = "not-a-token"
        response = self.client.post(reverse("auth-logout"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(self._cleared(response, REFRESH_COOKIE))

    def test_sign_out_without_any_session_is_harmless(self):
        response = self.client.post(reverse("auth-logout"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(self._cleared(response, ACCESS_COOKIE))
        self.assertFalse(ActivityLog.objects.filter(action="logout").exists())

    def test_a_repeated_sign_out_is_harmless(self):
        self.login("a@alpha.test")
        refresh = self.client.cookies[REFRESH_COOKIE].value
        self.client.post(reverse("auth-logout"))
        self.client.cookies[REFRESH_COOKIE] = refresh
        response = self.client.post(reverse("auth-logout"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(ActivityLog.objects.filter(action="logout").count(), 1)
