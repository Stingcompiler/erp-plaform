"""The frontend catch-all must never serve a file outside frontend/out.

Before this guard `serve_frontend` joined the export directory with whatever
path the URL carried, so ``/../../backend/.env`` returned the protected
environment file to an anonymous caller. These tests pin the containment.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from django.http import Http404
from django.test import RequestFactory, SimpleTestCase

from core import frontend


class FrontendPathContainmentTests(SimpleTestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        root = Path(self.tmp.name)
        self.dist = root / "out"
        self.dist.mkdir()
        (self.dist / "index.html").write_text("<html>home</html>")
        (self.dist / "dashboard").mkdir()
        (self.dist / "dashboard" / "index.html").write_text("<html>dash</html>")
        (self.dist / "about.html").write_text("<html>about</html>")
        # A file that sits beside the export, standing in for backend/.env.
        self.secret = root / ".env"
        self.secret.write_text("DJANGO_SECRET_KEY=leaked")
        self.patcher = mock.patch.object(frontend, "FRONTEND_DIST", self.dist)
        self.patcher.start()
        self.factory = RequestFactory()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def _get(self, path):
        with mock.patch.object(frontend, "_rewritten", return_value=None):
            return frontend.serve_frontend(self.factory.get("/" + path), path)

    def _body(self, response):
        if hasattr(response, "streaming_content"):
            return b"".join(response.streaming_content)
        return response.content

    def test_pages_inside_the_export_still_resolve(self):
        self.assertIn(b"home", self._body(self._get("")))
        self.assertIn(b"dash", self._body(self._get("dashboard")))
        self.assertIn(b"dash", self._body(self._get("dashboard/")))
        self.assertIn(b"about", self._body(self._get("about")))

    def test_dot_dot_segments_cannot_leave_the_export(self):
        for path in ("../.env", "../../.env", "dashboard/../../.env", "./../.env"):
            with self.subTest(path=path):
                with self.assertRaises(Http404):
                    self._get(path)

    def test_absolute_paths_are_refused(self):
        with self.assertRaises(Http404):
            self._get(str(self.secret))

    def test_unknown_page_falls_back_to_404_page_when_present(self):
        (self.dist / "404.html").write_text("<html>missing</html>")
        response = self._get("../.env")
        self.assertEqual(response.status_code, 404)
        self.assertIn(b"missing", self._body(response))
        self.assertNotIn(b"leaked", self._body(response))

    def test_encoded_traversal_through_the_url_resolver_is_refused(self):
        """The URL layer decodes %2e%2e before the view sees it."""
        (self.dist / "404.html").write_text("<html>missing</html>")
        with mock.patch.object(frontend, "_rewritten", return_value=None):
            with self.settings(DEBUG=False):
                response = self.client.get("/%2e%2e/%2e%2e/.env")
        self.assertEqual(response.status_code, 404)
        self.assertNotIn(b"leaked", self._body(response))
