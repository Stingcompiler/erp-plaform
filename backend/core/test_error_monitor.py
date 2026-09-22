"""Error monitoring: repeats fold into one row, the console reads it, and
the monitor itself can never make an outage worse.
"""

from unittest import mock

from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.http import Http404
from django.test import RequestFactory, TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User
from core.error_monitor import ErrorMonitorMiddleware
from core.models import ErrorEvent


def _boom():
    raise ValueError("boom")


def _capture(path="/api/sales/invoices/", exc=None):
    middleware = ErrorMonitorMiddleware(lambda request: None)
    request = RequestFactory().post(path)
    try:
        _boom()
    except ValueError as caught:
        middleware.process_exception(request, exc or caught)


@override_settings(DEBUG=False)
class ErrorCaptureTests(TestCase):
    def test_records_and_deduplicates(self):
        _capture()
        _capture()
        event = ErrorEvent.objects.get()
        self.assertEqual(event.count, 2)
        self.assertEqual(event.exc_type, "ValueError")
        self.assertEqual(event.message, "boom")
        self.assertEqual(event.method, "POST")
        self.assertIn("_boom", event.traceback)

    def test_expected_4xx_exceptions_are_not_recorded(self):
        # A visitor asking for a store slug that does not exist, a forbidden
        # page, a bad host: the right status code is the whole answer.
        for exc in (Http404("no such site"), PermissionDenied(), SuspiciousOperation()):
            _capture(path="/s/unknown-shop/", exc=exc)
        self.assertEqual(ErrorEvent.objects.count(), 0)
        # A real fault on the same path still lands.
        _capture(path="/s/unknown-shop/")
        self.assertEqual(ErrorEvent.objects.count(), 1)

    def test_recurrence_reopens_a_resolved_error(self):
        _capture()
        ErrorEvent.objects.update(resolved_at="2026-01-01T00:00:00Z")
        _capture()
        self.assertIsNone(ErrorEvent.objects.get().resolved_at)

    def test_different_paths_are_different_rows(self):
        _capture("/api/a/")
        _capture("/api/b/")
        self.assertEqual(ErrorEvent.objects.count(), 2)

    def test_monitor_failure_is_swallowed(self):
        with mock.patch("core.models.ErrorEvent.objects") as objects:
            objects.filter.side_effect = RuntimeError("db down")
            _capture()  # must not raise

    @override_settings(DEBUG=True)
    def test_debug_runs_are_not_recorded(self):
        _capture()
        self.assertEqual(ErrorEvent.objects.count(), 0)


@override_settings(DEBUG=False)
class ErrorApiTests(TestCase):
    URL = "/api/platform/errors/"

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(
            User.objects.create_superuser(email="root4@vezano.test", password="Root-passw0rd!")
        )
        _capture()

    def test_platform_admin_lists_and_resolves(self):
        listing = self.client.get(self.URL)
        self.assertEqual(listing.status_code, 200)
        rows = listing.json()["results"] if isinstance(listing.json(), dict) else listing.json()
        self.assertEqual(len(rows), 1)
        event_id = rows[0]["id"]

        resolved = self.client.post(f"{self.URL}{event_id}/resolve/")
        self.assertEqual(resolved.status_code, 200)
        self.assertIsNotNone(resolved.json()["resolved_at"])
        rows = self.client.get(self.URL).json()
        rows = rows["results"] if isinstance(rows, dict) else rows
        self.assertEqual(rows, [])
        rows = self.client.get(self.URL, {"all": "1"}).json()
        rows = rows["results"] if isinstance(rows, dict) else rows
        self.assertEqual(len(rows), 1)

    def test_tenant_user_is_refused(self):
        client = APIClient()
        client.force_authenticate(
            User.objects.create_user(email="user@x.test", password="User-passw0rd!")
        )
        self.assertEqual(client.get(self.URL).status_code, 403)
