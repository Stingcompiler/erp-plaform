"""The static export's PWA files must be served with types a browser accepts."""
import mimetypes

from django.test import SimpleTestCase

import core.frontend  # noqa: F401  (registers the manifest type on import)


class ManifestMimeTypeTests(SimpleTestCase):
    def test_webmanifest_type_registered(self):
        content_type, _ = mimetypes.guess_type("manifest.webmanifest")
        self.assertEqual(content_type, "application/manifest+json")
