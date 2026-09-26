"""The SEO control page end to end: the API the platform team uses, the
activity trail it leaves, and what the served pages show afterwards — the
export through core.frontend and the company pages through
website.public_pages."""
import tempfile

from django.core.cache import cache
from django.test import RequestFactory, override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import User
from core.frontend import FRONTEND_DIST, serve_frontend
from core.models import ActivityLog
from website.models import SeoPageOverride, SeoSettings, Website
from website import tests as website_tests

_png = website_tests._png


class SeoAdminBase(APITestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.root = User.objects.create_superuser("root@vezano.test", "secure-password")
        self.client.force_authenticate(self.root)

    def _invite(self, role):
        slug = role.lower().replace(" ", "-")
        response = self.client.post(
            reverse("platform-team-list"),
            {"email": f"{slug}@vezano.test", "full_name": role, "role": role}, format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        return User.objects.get(email=f"{slug}@vezano.test")


class SeoSettingsApiTests(SeoAdminBase):
    def test_settings_row_is_created_blank_on_first_read(self):
        response = self.client.get(reverse("platform-seo-settings"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["google_site_verification"], "")
        self.assertEqual(response.data["analytics_id"], "")
        self.assertEqual(response.data["default_og_image_url"], "")
        self.assertEqual(SeoSettings.objects.count(), 1)

    def test_patch_validates_and_logs(self):
        url = reverse("platform-seo-settings")
        bad = self.client.patch(url, {"analytics_id": "G-1<script>"}, format="json")
        self.assertEqual(bad.status_code, 400)
        bad = self.client.patch(url, {"google_site_verification": '"><script>'}, format="json")
        self.assertEqual(bad.status_code, 400)
        good = self.client.patch(
            url,
            {"google_site_verification": " tok-123 ", "analytics_id": "G-ABC123",
             "robots_extra": "Disallow: /old/"},
            format="json",
        )
        self.assertEqual(good.status_code, 200, good.data)
        self.assertEqual(good.data["google_site_verification"], "tok-123")
        row = ActivityLog.objects.get(entity_type="SeoSettings")
        self.assertEqual(row.action, "update")
        self.assertEqual(row.user, self.root)
        self.assertEqual(
            row.metadata["fields"], ["analytics_id", "google_site_verification", "robots_extra"]
        )
        # The platform activity page lists it.
        activity = self.client.get(
            reverse("platform-activity-list"), {"entity_type": "SeoSettings"}
        )
        self.assertEqual(activity.status_code, 200)
        self.assertEqual(activity.data["count"], 1)

    def test_default_share_image_upload_and_removal(self):
        with tempfile.TemporaryDirectory() as media:
            with override_settings(MEDIA_ROOT=media):
                url = reverse("platform-seo-settings-image")
                uploaded = self.client.post(url, {"image": _png(2400, 1260)}, format="multipart")
                self.assertEqual(uploaded.status_code, 200, uploaded.data)
                image_url = uploaded.data["default_og_image_url"]
                self.assertTrue(image_url.startswith("/media/public/seo/"), image_url)
                self.assertTrue(uploaded.data["default_og_image_url"].endswith(".webp"))
                settings_row = SeoSettings.load()
                from PIL import Image

                with Image.open(settings_row.default_og_image.path) as image:
                    self.assertEqual(image.format, "WEBP")
                    self.assertLessEqual(max(image.size), 1200)
                anon = self.client_class()
                path = settings_row.default_og_image.name.split("public/", 1)[1]
                self.assertEqual(anon.get(reverse("public-media", args=[path])).status_code, 200)
                removed = self.client.delete(url)
                self.assertEqual(removed.status_code, 200)
                self.assertEqual(removed.data["default_og_image_url"], "")
                self.assertEqual(
                    ActivityLog.objects.filter(entity_type="SeoSettings").count(), 2
                )

    def test_support_contact_is_public_and_validated(self):
        url = reverse("platform-seo-settings")
        anon = self.client_class()
        empty = anon.get(reverse("public-site-contact"))
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.json(), {"whatsapp": "", "phone": "", "email": ""})
        self.assertIn("max-age=300", empty["Cache-Control"])
        bad = self.client.patch(url, {"support_whatsapp": "call me"}, format="json")
        self.assertEqual(bad.status_code, 400)
        bad = self.client.patch(url, {"support_email": "not-an-email"}, format="json")
        self.assertEqual(bad.status_code, 400)
        good = self.client.patch(
            url,
            {"support_whatsapp": " +249  91 234 5678 ", "support_phone": "+249 18 300 0000",
             "support_email": "hello@vezano.app"},
            format="json",
        )
        self.assertEqual(good.status_code, 200, good.data)
        self.assertEqual(good.data["support_whatsapp"], "+249 91 234 5678")
        # Live for visitors at once (the save clears the cache).
        self.assertEqual(
            anon.get(reverse("public-site-contact")).json(),
            {"whatsapp": "+249 91 234 5678", "phone": "+249 18 300 0000",
             "email": "hello@vezano.app"},
        )
        self.assertEqual(ActivityLog.objects.filter(entity_type="SeoSettings").count(), 1)

    def test_tenant_user_is_refused(self):
        from org.models import Company

        company = Company.objects.create(name="Tenant")
        owner = User.objects.create_user("owner@tenant.test", "secure-password", company=company)
        self.client.force_authenticate(owner)
        self.assertEqual(self.client.get(reverse("platform-seo-settings")).status_code, 403)
        self.assertEqual(self.client.get(reverse("platform-seo-override-list")).status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(reverse("platform-seo-settings")).status_code, 401)


class SeoOverrideApiTests(SeoAdminBase):
    def test_crud_normalises_the_path_and_logs_each_step(self):
        url = reverse("platform-seo-override-list")
        created = self.client.post(
            url, {"path": "pricing/", "language": "ar", "title": "الأسعار", "noindex": False},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data["path"], "/pricing")
        # Same page, same language: refused; the other language is fine.
        dup = self.client.post(url, {"path": "/pricing", "language": "ar"}, format="json")
        self.assertEqual(dup.status_code, 400)
        other = self.client.post(url, {"path": "/pricing", "language": "en"}, format="json")
        self.assertEqual(other.status_code, 201)
        bad = self.client.post(url, {"path": "/pricing?x=1", "language": "both"}, format="json")
        self.assertEqual(bad.status_code, 400)
        bad = self.client.post(
            url, {"path": "/x", "language": "both", "canonical": "not a url"}, format="json"
        )
        self.assertEqual(bad.status_code, 400)

        pk = created.data["id"]
        updated = self.client.patch(
            reverse("platform-seo-override-detail", args=[pk]),
            {"description": "وصف", "noindex": True}, format="json",
        )
        self.assertEqual(updated.status_code, 200, updated.data)
        listed = self.client.get(url)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual([row["path"] for row in listed.data], ["/pricing", "/pricing"])
        deleted = self.client.delete(reverse("platform-seo-override-detail", args=[pk]))
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(SeoPageOverride.objects.count(), 1)

        rows = ActivityLog.objects.filter(entity_type="SeoPageOverride").order_by("pk")
        self.assertEqual([r.action for r in rows], ["create", "create", "update", "delete"])
        self.assertEqual(rows[2].metadata["fields"], ["description", "noindex"])
        self.assertEqual(rows[3].metadata["path"], "/pricing")
        self.assertEqual(rows[3].metadata["language"], "ar")

    def test_support_agent_reads_but_cannot_write(self):
        agent = self._invite("Support Agent")
        marketing = self._invite("Marketing Manager")
        url = reverse("platform-seo-override-list")
        self.client.force_authenticate(agent)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.post(url, {"path": "/x"}, format="json").status_code, 403)
        self.assertEqual(
            self.client.patch(reverse("platform-seo-settings"), {"analytics_id": "G-1"},
                              format="json").status_code, 403,
        )
        self.client.force_authenticate(marketing)
        self.assertEqual(self.client.post(url, {"path": "/x"}, format="json").status_code, 201)


@override_settings(DEBUG=False)
class ServedExportTests(SeoAdminBase):
    """What a visitor gets from the export once the team has set things."""

    def setUp(self):
        super().setUp()
        if not (FRONTEND_DIST / "index.html").is_file():
            self.skipTest("frontend/out is not built")
        self.factory = RequestFactory()

    def _get(self, path):
        response = serve_frontend(self.factory.get(f"/{path}"), path)
        body = (
            b"".join(response.streaming_content) if response.streaming else response.content
        ).decode()
        return response, body

    def test_untouched_settings_serve_the_file_byte_for_byte(self):
        # Contact details alone do not touch the export: they are read by
        # the page over the API, not injected.
        self.client.patch(
            reverse("platform-seo-settings"), {"support_whatsapp": "+249912345678"},
            format="json",
        )
        original = (FRONTEND_DIST / "index.html").read_text(encoding="utf-8")
        response, body = self._get("")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.streaming)
        self.assertEqual(body, original)
        self.assertEqual(response["Cache-Control"], "no-cache, must-revalidate")
        _, robots = self._get("robots.txt")
        self.assertEqual(robots, (FRONTEND_DIST / "robots.txt").read_text(encoding="utf-8"))

    def test_overrides_and_site_tags_reach_the_served_page(self):
        self.client.patch(
            reverse("platform-seo-settings"),
            {"google_site_verification": "goog-1", "bing_site_verification": "bing-1",
             "analytics_id": "G-ABC123", "robots_extra": "Disallow: /old/\n"},
            format="json",
        )
        self.client.post(
            reverse("platform-seo-override-list"),
            {"path": "/pricing", "language": "ar", "title": "أسعار فيزانو برو",
             "description": "وصف الأسعار", "noindex": True,
             "canonical": "https://vezano.app/pricing/"},
            format="json",
        )
        self.client.post(
            reverse("platform-seo-override-list"),
            {"path": "/", "language": "both", "title": "Home override"}, format="json",
        )
        response, pricing = self._get("pricing")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.streaming)
        self.assertEqual(response["Content-Type"], "text/html")
        self.assertEqual(response["Cache-Control"], "no-cache, must-revalidate")
        self.assertIn("<title>أسعار فيزانو برو</title>", pricing)
        self.assertIn('<meta name="description" content="وصف الأسعار"/>', pricing)
        self.assertIn('<meta name="robots" content="noindex, nofollow"/>', pricing)
        self.assertIn('<meta name="google-site-verification" content="goog-1"/>', pricing)
        self.assertIn('<meta name="msvalidate.01" content="bing-1"/>', pricing)
        self.assertIn("gtag/js?id=G-ABC123", pricing)
        # The Arabic override does not touch the English edition; site tags do.
        _, english = self._get("en/pricing")
        self.assertNotIn("أسعار فيزانو برو", english)
        self.assertIn('<meta name="google-site-verification" content="goog-1"/>', english)
        # "both" applies to either edition.
        _, home_ar = self._get("")
        _, home_en = self._get("en")
        self.assertIn("<title>Home override</title>", home_ar)
        self.assertIn("<title>Home override</title>", home_en)
        # Hashed assets are never rewritten.
        css = next((FRONTEND_DIST / "_next/static/css").glob("*.css"))
        asset, _ = self._get(f"_next/static/css/{css.name}")
        self.assertTrue(asset.streaming)
        self.assertIn("immutable", asset["Cache-Control"])
        _, robots = self._get("robots.txt")
        self.assertTrue(robots.endswith("\n\nDisallow: /old/\n"))
        self.assertIn("Sitemap: https://vezano.app/sitemap.xml", robots)

    def test_change_is_visible_after_the_cache_is_invalidated(self):
        self._get("pricing")  # warms the cache with "nothing set"
        self.client.post(
            reverse("platform-seo-override-list"),
            {"path": "/pricing", "language": "both", "title": "Fresh"}, format="json",
        )
        _, body = self._get("pricing")
        self.assertIn("<title>Fresh</title>", body)


class CompanyPageSeoTests(website_tests.PublicSiteTests):
    """The Django-rendered /s/ pages read the same settings and overrides."""

    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)
        self._media = tempfile.TemporaryDirectory()
        self._override = override_settings(MEDIA_ROOT=self._media.name)
        self._override.enable()
        self.addCleanup(self._override.disable)
        self.addCleanup(self._media.cleanup)

    def test_company_page_without_settings_is_unchanged(self):
        self._build_and_publish()
        html = self.client_class().get(
            reverse("public-site-page", args=[self.company_a.slug])
        ).content.decode()
        self.assertIn("<title>Alpha Store</title>", html)
        self.assertIn('<meta name="robots" content="index, follow">', html)
        self.assertNotIn("google-site-verification", html)
        self.assertNotIn("googletagmanager", html)
        self.assertNotIn("og:image", html)

    def test_company_page_and_directory_apply_override_and_site_tags(self):
        self._build_and_publish()
        slug = self.company_a.slug
        settings_row = SeoSettings.load()
        settings_row.google_site_verification = "goog-2"
        settings_row.analytics_id = "G-XYZ"
        settings_row.save()
        SeoPageOverride.objects.create(
            path=f"/s/{slug}/", language="both", title="متجر ألفا الرسمي",
            description="وصف مخصص", canonical="https://vezano.app/s/alpha/",
        )
        SeoPageOverride.objects.create(path="/s", language="ar", noindex=True)
        anon = self.client_class()
        html = anon.get(reverse("public-site-page", args=[slug])).content.decode()
        self.assertIn("<title>متجر ألفا الرسمي</title>", html)
        self.assertIn('<meta property="og:title" content="متجر ألفا الرسمي">', html)
        self.assertIn('<meta name="description" content="وصف مخصص">', html)
        self.assertIn('<link rel="canonical" href="https://vezano.app/s/alpha/">', html)
        self.assertIn('<meta name="robots" content="index, follow">', html)
        self.assertIn('<meta name="google-site-verification" content="goog-2">', html)
        self.assertIn("gtag/js?id=G-XYZ", html)
        directory = anon.get(reverse("public-site-directory")).content.decode()
        self.assertIn('<meta name="robots" content="noindex, nofollow">', directory)
        self.assertIn('<meta name="google-site-verification" content="goog-2">', directory)
        # The default share image fills a page that has no cover or logo.
        self.client.force_authenticate(User.objects.create_superuser("root@vezano.test", "x"))
        uploaded = self.client.post(
            reverse("platform-seo-settings-image"), {"image": _png(1200, 630)}, format="multipart"
        )
        self.assertEqual(uploaded.status_code, 200, uploaded.data)
        html = anon.get(reverse("public-site-page", args=[slug])).content.decode()
        image_url = uploaded.data["default_og_image_url"]
        self.assertIn(f'<meta property="og:image" content="https://vezano.app{image_url}">', html)
        self.assertTrue(Website.objects.get(company=self.company_a).is_published)
