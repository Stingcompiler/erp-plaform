"""The hosted SaaS answers on the canonical apex domain, its www alias and the
original enterprise.* subdomain, and the crawler files ship with the export."""
from django.conf import settings
from django.test import RequestFactory, SimpleTestCase, override_settings

from core.frontend import FRONTEND_DIST, serve_frontend

HOSTS = ("vezano.app", "www.vezano.app", "enterprise.vezano.app")


class PublicHostTests(SimpleTestCase):
    def test_every_public_host_is_allowed(self):
        for host in HOSTS:
            self.assertIn(host, settings.ALLOWED_HOSTS)
            self.assertIn(f"https://{host}", settings.CSRF_TRUSTED_ORIGINS)

    def test_canonical_host_is_the_apex_domain(self):
        self.assertEqual(settings.VEZANO_CANONICAL_HOST, "vezano.app")
        self.assertEqual(settings.VEZANO_PUBLIC_HOSTS[0], settings.VEZANO_CANONICAL_HOST)

    def test_health_answers_on_each_host(self):
        for host in HOSTS:
            response = self.client.get("/api/health/", HTTP_HOST=host)
            self.assertEqual(response.status_code, 200, host)


@override_settings(DEBUG=False)
class CrawlerFileTests(SimpleTestCase):
    """robots.txt and sitemap.xml are written by the Next export (app/robots.js,
    app/sitemap.js) and served from the export root like any other file."""

    def setUp(self):
        if not (FRONTEND_DIST / "index.html").is_file():
            self.skipTest("frontend/out is not built")
        self.factory = RequestFactory()

    def _get(self, path):
        response = serve_frontend(self.factory.get(f"/{path}"), path)
        return response, b"".join(response.streaming_content).decode()

    def test_robots_points_at_the_canonical_sitemap(self):
        response, body = self._get("robots.txt")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/plain")
        self.assertIn("Sitemap: https://vezano.app/sitemap.xml", body)
        self.assertIn("Disallow: /api/", body)
        self.assertIn("Disallow: /dashboard/", body)

    def test_sitemap_lists_only_canonical_public_pages(self):
        response, body = self._get("sitemap.xml")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/xml")
        for path in ("/", "/product/", "/pricing/", "/register/"):
            self.assertIn(f"<loc>https://vezano.app{path}</loc>", body)
        self.assertNotIn("enterprise.vezano.app", body)
        self.assertNotIn("/dashboard/", body)

    def test_marketing_pages_carry_canonical_and_app_pages_noindex(self):
        public = ("index.html", "pricing/index.html", "product/index.html", "register/index.html")
        for page in public:
            html = (FRONTEND_DIST / page).read_text()
            expected = "https://vezano.app/" + page.replace("index.html", "")
            self.assertIn(f'<link rel="canonical" href="{expected}"', html, page)
            self.assertNotIn("noindex", html, page)
        for page in ("login/index.html", "dashboard/index.html"):
            html = (FRONTEND_DIST / page).read_text()
            self.assertIn('<meta name="robots" content="noindex', html, page)
            self.assertNotIn('rel="canonical"', html, page)
