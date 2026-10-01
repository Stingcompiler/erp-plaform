"""SEO redirects (phase C): the stored form of a path, every rule a
redirect must pass, serving them from the export and the /s/ pages, the
hit counter, the API with its test/check/import actions, the health flags,
and the one additive migration they need."""
import io
import re
import tempfile
from pathlib import Path
from unittest import mock

from django.core.cache import cache
from django.core.management import call_command
from django.db import DatabaseError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import User
from core.frontend import FRONTEND_DIST
from core.models import ActivityLog
from org.models import Company
from website import redirects, seo_health
from website.models import SeoRedirect, Website
from website.redirects import RedirectPathError, normalize_source, request_key

ORIGIN = "https://vezano.app"


class NormalisationTests(SimpleTestCase):
    def test_paths_collapse_to_one_stored_form(self):
        for typed in ("old-page", "/old-page", "/old-page/", " /Old-Page// ", "/old-page//"):
            self.assertEqual(normalize_source(typed), "/old-page", typed)
        self.assertEqual(normalize_source("/a//b///c/"), "/a/b/c")
        self.assertEqual(normalize_source("/EN/Old/"), "/en/old")
        self.assertEqual(normalize_source("/"), "/")
        # Percent-encoded Arabic is stored decoded, the way Django hands
        # request.path to the lookup.
        self.assertEqual(normalize_source("/%D9%85%D8%AA%D8%AC%D8%B1/"), "/متجر")
        self.assertEqual(request_key("/متجر/"), "/متجر")
        self.assertEqual(request_key("/Old-Page/"), "/old-page")

    def test_a_full_address_on_the_site_keeps_only_its_path(self):
        self.assertEqual(normalize_source("https://vezano.app/en/Old/"), "/en/old")
        self.assertEqual(normalize_source("https://www.vezano.app/x"), "/x")
        self.assertEqual(normalize_source("//vezano.app/x/"), "/x")

    def test_hosts_queries_and_odd_characters_are_refused(self):
        for bad in (
            "", "   ", "https://example.com/old", "/old?utm=1", "/old#top",
            "https://vezano.app/old?x=1", "/a b", "/a%20b", "/<script>", '/a"b',
        ):
            with self.assertRaises(RedirectPathError, msg=bad):
                normalize_source(bad)
        with self.assertRaises(RedirectPathError):
            normalize_source("/" + "a" * 300)

    def test_query_is_kept_after_the_targets_own(self):
        self.assertEqual(redirects.with_query("/new/", ""), "/new/")
        self.assertEqual(redirects.with_query("/new/", "utm=1&b=2"), "/new/?utm=1&b=2")
        self.assertEqual(redirects.with_query("/new/?a=1#top", "b=2"), "/new/?a=1&b=2#top")
        self.assertEqual(
            redirects.with_query("https://vezano.app/p", "x=1"), "https://vezano.app/p?x=1"
        )


class RuleTests(SimpleTestCase):
    """check_redirect on its own: each rule, with the other active
    redirects passed in."""

    def check(self, source, target, **kwargs):
        return redirects.check_redirect(normalize_source(source), target, **kwargs)

    def test_a_plain_redirect_passes(self):
        self.assertEqual(self.check("/old", "/pricing/"), {})
        self.assertEqual(self.check("/en/old", "/en/pricing/"), {})
        self.assertEqual(self.check("/old", "https://vezano.app/pricing/"), {})
        self.assertEqual(self.check("/s/old-shop", "/s/new-shop/"), {})
        self.assertEqual(self.check("/s/old-shop/promo", "/s/new-shop/"), {})

    def test_self_redirect(self):
        self.assertIn("target", self.check("/old", "/old/"))
        self.assertIn("target", self.check("/old", "/OLD?x=1"))
        self.assertIn("target", self.check("/old", "https://vezano.app/old/"))

    def test_loops_and_chains_are_refused(self):
        others = [("/b", "/c"), ("/x", "/a")]
        # The target is itself redirected: a chain (or a loop back here).
        self.assertIn("target", self.check("/a", "/b/", others=others))
        # Another redirect already lands on this source: a chain.
        errors = self.check("/a", "/d/", others=others)
        self.assertIn("source_path", errors)
        # A two-step loop: /x -> /a exists; /a -> /x is both.
        errors = self.check("/a", "/x", others=others)
        self.assertIn("target", errors)
        self.assertIn("source_path", errors)
        # An inactive redirect is not part of any chain yet.
        self.assertEqual(self.check("/a", "/b/", others=others, is_active=False), {})
        # External targets do not chain.
        self.assertEqual(
            self.check("/n", "/c", others=[("/q", None)], allow_external=True), {}
        )

    def test_protected_paths(self):
        for source in (
            "/api/platform/overview", "/api", "/admin/", "/_next/static/x.js", "/static/a.css",
            "/media/public/x.png", "/sw.js", "/manifest.webmanifest", "/robots.txt",
            "/sitemap.xml", "/sitemap-sites.xml", "/icons/icon-192.png", "/favicon.ico",
            "/login/", "/dashboard", "/sales/invoices", "/platform", "/platform-seo/",
            "/platform-analytics", "/en/login", "/en/dashboard/", "/s", "/s/", "/", "/en",
            "/forgot-password", "/reset-password/",
        ):
            errors = self.check(source, "/pricing/")
            self.assertIn("source_path", errors, source)
        # Company pages under /s/ are fine, and so are paths that only start
        # with the same letters as a protected one.
        for source in ("/s/shop", "/apiary", "/salesman-guide", "/administration"):
            self.assertNotIn("source_path", self.check(source, "/pricing/"), source)

    def test_robots_disallows_extend_the_protected_list(self):
        prefixes = redirects.PROTECTED_PREFIXES + ("/new-app-route",)
        self.assertIn("source_path", self.check("/new-app-route/x", "/", prefixes=prefixes))
        self.assertNotIn("source_path", self.check("/new-app-route/x", "/"))

    def test_external_and_malformed_targets(self):
        self.assertIn("target", self.check("/old", "https://example.com/"))
        self.assertEqual(self.check("/old", "https://example.com/", allow_external=True), {})
        for bad in ("", "pricing", "//example.com/x", "http://vezano.app/x",
                    "javascript:alert(1)", "https://user:pw@vezano.app/", "/a b",
                    "ftp://vezano.app/x"):
            self.assertIn("target", self.check("/old", bad, allow_external=True), bad)
        self.assertIn("status_code", self.check("/old", "/new", status_code=303))
        self.assertEqual(self.check("/old", "/new", status_code=302), {})

    def test_app_pages_of_the_export_are_refused(self):
        errors = self.check("/brand-new-app", "/", app_page=lambda key: key == "/brand-new-app")
        self.assertIn("source_path", errors)


class RedirectBase(APITestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.root = User.objects.create_superuser("root@vezano.test", "secure-password")
        self.client.force_authenticate(self.root)
        self.url = reverse("platform-seo-redirect-list")

    def _invite(self, role):
        slug = role.lower().replace(" ", "-")
        response = self.client.post(
            reverse("platform-team-list"),
            {"email": f"{slug}@vezano.test", "full_name": role, "role": role}, format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        return User.objects.get(email=f"{slug}@vezano.test")

    def create(self, source, target, **extra):
        response = self.client.post(
            self.url, {"source_path": source, "target": target, **extra}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)
        return response.data


class RedirectApiTests(RedirectBase):
    def test_crud_normalises_validates_and_logs(self):
        created = self.create(" /Old-Pricing/ ", "/pricing/", note="renamed")
        self.assertEqual(created["source_path"], "/old-pricing")
        self.assertEqual(created["status_code"], 301)
        self.assertTrue(created["is_active"])
        self.assertEqual(created["hits"], 0)
        self.assertEqual(created["created_by_name"], "root@vezano.test")
        # Same source in another spelling: refused.
        dup = self.client.post(
            self.url, {"source_path": "/old-pricing", "target": "/"}, format="json"
        )
        self.assertEqual(dup.status_code, 400)
        self.assertIn("source_path", dup.data)
        # A chain onto it, and from its target, are refused.
        chain = self.client.post(
            self.url, {"source_path": "/older", "target": "/old-pricing/"}, format="json"
        )
        self.assertEqual(chain.status_code, 400)
        self.assertIn("target", chain.data)
        protected = self.client.post(
            self.url, {"source_path": "/api/x", "target": "/"}, format="json"
        )
        self.assertEqual(protected.status_code, 400)
        external = self.client.post(
            self.url, {"source_path": "/blog", "target": "https://blog.example.com/"},
            format="json",
        )
        self.assertEqual(external.status_code, 400)
        self.create("/blog", "https://blog.example.com/", allow_external=True, status_code=302)

        detail = reverse("platform-seo-redirect-detail", args=[created["id"]])
        updated = self.client.patch(detail, {"is_active": False}, format="json")
        self.assertEqual(updated.status_code, 200, updated.data)
        self.assertFalse(updated.data["is_active"])
        # Retargeting it onto itself is still caught when partial.
        selfie = self.client.patch(detail, {"target": "/old-pricing"}, format="json")
        self.assertEqual(selfie.status_code, 400)
        listed = self.client.get(self.url)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual([row["source_path"] for row in listed.data], ["/blog", "/old-pricing"])
        self.assertEqual(self.client.delete(detail).status_code, 204)
        rows = ActivityLog.objects.filter(entity_type="SeoRedirect").order_by("pk")
        self.assertEqual([row.action for row in rows], ["create", "create", "update", "delete"])
        self.assertEqual(rows[2].metadata["fields"], ["is_active"])
        self.assertEqual(rows[3].metadata["source_path"], "/old-pricing")

    def test_check_reports_errors_without_saving(self):
        url = reverse("platform-seo-redirect-check")
        good = self.client.post(url, {"source_path": "Old/", "target": "/pricing/"}, format="json")
        self.assertEqual(good.status_code, 200)
        self.assertTrue(good.data["valid"])
        self.assertEqual(good.data["source_path"], "/old")
        bad = self.client.post(url, {"source_path": "/login", "target": "/login"}, format="json")
        self.assertFalse(bad.data["valid"])
        self.assertIn("source_path", bad.data["errors"])
        existing = self.create("/old", "/pricing/")
        # Editing a row is checked against the others, not itself.
        editing = self.client.post(
            url, {"id": existing["id"], "source_path": "/old", "target": "/product/"},
            format="json",
        )
        self.assertTrue(editing.data["valid"], editing.data)
        self.assertFalse(self.client.post(
            url, {"source_path": "/old", "target": "/product/"}, format="json"
        ).data["valid"])
        self.assertEqual(SeoRedirect.objects.count(), 1)

    def test_test_action_says_what_a_url_gets(self):
        url = reverse("platform-seo-redirect-test")
        self.create("/old", "/pricing/?ref=old")
        hit = self.client.get(url, {"path": "https://vezano.app/OLD/?utm=x"})
        self.assertEqual(hit.status_code, 200)
        self.assertEqual(hit.data["outcome"], "redirect")
        self.assertEqual(hit.data["status_code"], 301)
        self.assertEqual(hit.data["location"], "/pricing/?ref=old&utm=x")
        self.assertEqual(self.client.get(url, {"path": "/nothing"}).data["outcome"], "none")
        self.assertEqual(self.client.get(url, {"path": "/api/x"}).data["outcome"], "protected")
        self.assertEqual(
            self.client.get(url, {"path": "https://example.com/x"}).data["outcome"], "invalid"
        )
        SeoRedirect.objects.filter(source_path="/old").update(is_active=False)
        self.assertEqual(self.client.get(url, {"path": "/old"}).data["outcome"], "inactive")
        self.assertEqual(self.client.get(url).status_code, 400)

    def test_permissions(self):
        agent = self._invite("Support Agent")
        marketing = self._invite("Marketing Manager")
        self.create("/old", "/pricing/")
        self.client.force_authenticate(agent)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("platform-seo-redirect-test"), {"path": "/old"}).status_code,
            200,
        )
        for url, body in (
            (self.url, {"source_path": "/x", "target": "/"}),
            (reverse("platform-seo-redirect-check"), {"source_path": "/x", "target": "/"}),
            (reverse("platform-seo-redirect-import"), {"csv": "/x,/", "dry_run": True}),
        ):
            self.assertEqual(self.client.post(url, body, format="json").status_code, 403, url)
        self.client.force_authenticate(marketing)
        self.assertEqual(
            self.client.post(self.url, {"source_path": "/x", "target": "/"}, format="json")
            .status_code, 201,
        )
        company = Company.objects.create(name="Tenant")
        owner = User.objects.create_user("owner@tenant.test", "secure-password", company=company)
        self.client.force_authenticate(owner)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url).status_code, 401)


class CsvImportTests(RedirectBase):
    CSV = (
        "source,target,status\n"
        "/old-a,/pricing/,301\n"
        "https://vezano.app/Old-B/,/product/,302\n"
        "/login,/pricing/,301\n"           # protected
        "/old-c,https://example.com/,\n"   # external
        "/old-a,/compare/,301\n"           # duplicate in the file
        "/old-d,/old-a/,301\n"             # chain onto a row of the file
        "/old-e,/pricing/,307\n"           # bad status
        "/existing,/pricing/,301\n"        # already stored
        "\n"
    )

    def setUp(self):
        super().setUp()
        self.import_url = reverse("platform-seo-redirect-import")
        self.create("/existing", "/product/")

    def test_dry_run_reports_each_row_and_writes_nothing(self):
        response = self.client.post(
            self.import_url, {"csv": self.CSV, "dry_run": True}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        report = response.data
        self.assertTrue(report["dry_run"])
        self.assertEqual((report["total"], report["valid"], report["invalid"]), (8, 2, 6))
        by_line = {row["line"]: row for row in report["rows"]}
        self.assertEqual(by_line[2]["errors"], {})
        self.assertEqual(by_line[3]["source_path"], "/old-b")
        self.assertEqual(by_line[3]["status_code"], 302)
        self.assertIn("source_path", by_line[4]["errors"])
        self.assertIn("target", by_line[5]["errors"])
        # "(line 2)" in either language.
        self.assertRegex(by_line[6]["errors"]["source_path"], r"\b2\)")
        self.assertIn("target", by_line[7]["errors"])
        self.assertIn("status_code", by_line[8]["errors"])
        self.assertIn("source_path", by_line[9]["errors"])
        self.assertEqual(SeoRedirect.objects.count(), 1)

    def test_import_is_all_or_nothing(self):
        refused = self.client.post(self.import_url, {"csv": self.CSV}, format="json")
        self.assertEqual(refused.status_code, 400)
        self.assertEqual(refused.data["created"], 0)
        self.assertEqual(SeoRedirect.objects.count(), 1)

        upload = io.BytesIO(
            "﻿source,target,status\n/old-a,/pricing/,301\n/en/old-b/,/en/product/,302\n"
            .encode("utf-8")
        )
        upload.name = "redirects.csv"
        done = self.client.post(self.import_url, {"file": upload}, format="multipart")
        self.assertEqual(done.status_code, 201, done.data)
        self.assertEqual(done.data["created"], 2)
        self.assertEqual(
            sorted(SeoRedirect.objects.values_list("source_path", "status_code")),
            [("/en/old-b", 302), ("/existing", 301), ("/old-a", 301)],
        )
        self.assertEqual(SeoRedirect.objects.get(source_path="/old-a").created_by, self.root)
        row = ActivityLog.objects.get(entity_type="SeoRedirect", action="import")
        self.assertEqual(row.metadata["created"], 2)

    def test_empty_and_unreadable_files(self):
        self.assertEqual(
            self.client.post(self.import_url, {"csv": "source,target\n"}, format="json")
            .status_code, 400,
        )
        upload = io.BytesIO("/a,/b\n".encode("utf-16"))
        upload.name = "x.csv"
        self.assertEqual(
            self.client.post(self.import_url, {"file": upload}, format="multipart").status_code,
            400,
        )


class ServingTests(RedirectBase):
    """What a visitor gets, through the real URL routing."""

    def setUp(self):
        super().setUp()
        if not (FRONTEND_DIST / "index.html").is_file():
            self.skipTest("frontend/out is not built")
        self.anon = self.client_class()

    def test_export_redirects_keep_the_query(self):
        self.create("/old-pricing", "/pricing/")
        self.create("/en/old", "/en/pricing/", status_code=302)
        response = self.anon.get("/old-pricing/?utm_source=x&b=2")
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], "/pricing/?utm_source=x&b=2")
        self.assertEqual(response["Cache-Control"], "public, max-age=300")
        # Trailing slash and case do not matter.
        self.assertEqual(self.anon.get("/OLD-PRICING")["Location"], "/pricing/")
        temporary = self.anon.get("/en/old/?a=1")
        self.assertEqual(temporary.status_code, 302)
        self.assertEqual(temporary["Location"], "/en/pricing/?a=1")
        self.assertEqual(temporary["Cache-Control"], "no-store")
        # HEAD too, but a POST is never redirected.
        self.assertEqual(self.anon.head("/old-pricing/").status_code, 301)
        self.assertNotIn(self.anon.post("/old-pricing/").status_code, (301, 302))

    def test_an_existing_page_can_be_moved_and_inactive_rows_do_nothing(self):
        self.assertEqual(self.anon.get("/product/").status_code, 200)
        created = self.create("/product", "/pricing/")
        self.assertEqual(self.anon.get("/product/").status_code, 301)
        self.client.patch(
            reverse("platform-seo-redirect-detail", args=[created["id"]]),
            {"is_active": False}, format="json",
        )
        # Saving cleared the cached map: the page is back at once.
        self.assertEqual(self.anon.get("/product/").status_code, 200)

    def test_company_pages_redirect_with_the_query(self):
        alpha = Company.objects.create(name="Alpha", slug="alpha")
        Website.objects.create(company=alpha, business_name="Alpha", is_published=True)
        self.create("/s/old-alpha", "/s/alpha/")
        self.create("/s/alpha/old-promo", "/s/alpha/", status_code=302)
        self.create("/s/alpha-shop", "/s/alpha/")
        response = self.anon.get("/s/old-alpha/?ref=qr")
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], "/s/alpha/?ref=qr")
        self.assertEqual(response["Cache-Control"], "public, max-age=300")
        # A path no /s/ view serves still finds its redirect.
        promo = self.anon.get("/s/alpha/old-promo/?x=1")
        self.assertEqual(promo.status_code, 302)
        self.assertEqual(promo["Location"], "/s/alpha/?x=1")
        self.assertEqual(promo["Cache-Control"], "no-store")
        # A slug view with a redirect answers it before looking the site up.
        self.assertEqual(self.anon.get("/s/alpha-shop/").status_code, 301)
        # Untouched paths behave as before.
        self.assertEqual(self.anon.get("/s/alpha/").status_code, 200)
        self.assertEqual(self.anon.get("/s/alpha/nothing-here/").status_code, 404)
        self.assertEqual(self.anon.get("/s/no-such-shop/").status_code, 404)

    def test_api_and_app_routes_are_never_redirected(self):
        # Rows that slipped past validation (written straight to the table).
        for source in ("/api/public/plans", "/login", "/dashboard", "/platform-seo",
                       "/sw.js", "/robots.txt", "/s", "/", "/en/login"):
            SeoRedirect.objects.create(source_path=source, target="/pricing/")
        for path in ("/api/public/plans/", "/login/", "/dashboard/", "/platform-seo/",
                     "/sw.js", "/robots.txt", "/s/", "/", "/en/login/"):
            response = self.anon.get(path)
            self.assertNotIn(response.status_code, (301, 302), path)
            self.assertIsNone(redirects.lookup(request_key(path)), path)
        self.assertFalse(SeoRedirect.objects.filter(hits__gt=0).exists())

    def test_hits_are_counted_and_a_failed_count_still_redirects(self):
        created = self.create("/old", "/pricing/")
        self.anon.get("/old/")
        self.anon.get("/old/?x=1")
        row = SeoRedirect.objects.get(pk=created["id"])
        self.assertEqual(row.hits, 2)
        self.assertIsNotNone(row.last_hit_at)
        listed = self.client.get(self.url).data
        self.assertEqual(listed[0]["hits"], 2)
        with mock.patch.object(
            SeoRedirect.objects, "filter", side_effect=DatabaseError("locked")
        ):
            self.assertEqual(self.anon.get("/old/").status_code, 301)
        self.assertEqual(SeoRedirect.objects.get(pk=created["id"]).hits, 2)

    def test_a_missing_table_serves_pages_untouched(self):
        with mock.patch.object(
            SeoRedirect.objects, "filter", side_effect=DatabaseError("no such table")
        ):
            cache.clear()
            self.assertEqual(redirects.load_map(), {})


class HealthFlagTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.dist = Path(tempfile.mkdtemp())
        (self.dist / "index.html").write_text("<html></html>", encoding="utf-8")
        for page in ("pricing", "old"):
            (self.dist / page).mkdir()
            (self.dist / page / "index.html").write_text("<html></html>", encoding="utf-8")
        urls = "".join(
            f"<url><loc>{ORIGIN}{path}</loc></url>" for path in ("/", "/pricing/", "/old/")
        )
        (self.dist / "sitemap.xml").write_text(
            f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>',
            encoding="utf-8",
        )

    def test_sources_in_a_sitemap_and_targets_without_a_page(self):
        shop = Company.objects.create(name="Shop", slug="shop")
        Website.objects.create(
            company=shop, business_name="Shop", is_published=True, list_in_directory=True
        )
        SeoRedirect.objects.create(source_path="/old", target="/pricing/")
        SeoRedirect.objects.create(source_path="/gone", target="/nowhere/")
        SeoRedirect.objects.create(source_path="/s/shop", target="/s/closed-shop/")
        SeoRedirect.objects.create(source_path="/fine", target="/pricing/?x=1")
        SeoRedirect.objects.create(source_path="/out", target="https://example.com/",
                                   allow_external=True)
        SeoRedirect.objects.create(source_path="/off", target="/nowhere/", is_active=False)
        rows = {row["source_path"]: row for row in seo_health.check_redirects(self.dist, ORIGIN)}
        self.assertNotIn("/off", rows)
        codes = {path: [i["code"] for i in row["issues"]] for path, row in rows.items()}
        self.assertEqual(codes["/old"], ["redirect_in_sitemap"])
        self.assertEqual(rows["/old"]["issues"][0]["params"], {"sitemap": "sitemap.xml"})
        self.assertEqual(codes["/gone"], ["redirect_target_missing"])
        self.assertEqual(rows["/gone"]["severity"], "error")
        self.assertEqual(
            codes["/s/shop"], ["redirect_in_sitemap", "redirect_target_missing"]
        )
        self.assertEqual(rows["/s/shop"]["issues"][0]["params"], {"sitemap": "sitemap-sites.xml"})
        self.assertEqual(codes["/fine"], [])
        self.assertEqual(codes["/out"], [])

    def test_the_report_carries_the_redirects(self):
        SeoRedirect.objects.create(source_path="/gone", target="/nowhere/")
        with mock.patch("core.frontend.FRONTEND_DIST", self.dist):
            report = seo_health.build_report()
        self.assertEqual([row["source_path"] for row in report["redirects"]], ["/gone"])
        self.assertIn(
            ("redirect_target_missing", "error"),
            {(item["code"], item["severity"]) for item in report["summary"]["issues"]},
        )


class MigrationTests(TestCase):
    def test_exactly_one_additive_migration(self):
        folder = Path(__file__).resolve().parent / "migrations"
        names = sorted(
            path.name for path in folder.glob("*.py") if re.match(r"^\d{4}_", path.name)
        )
        after_phase_b = [name for name in names if name > "0020_pricing_display.py"]
        self.assertEqual(after_phase_b, ["0021_seoredirect.py"])
        from importlib import import_module

        migration = import_module("website.migrations.0021_seoredirect").Migration
        self.assertEqual(
            [type(op).__name__ for op in migration.operations], ["CreateModel"]
        )
        self.assertTrue(all(op.reversible for op in migration.operations))

    def test_models_match_the_migrations(self):
        out = io.StringIO()
        try:
            call_command("makemigrations", "--check", "--dry-run", stdout=out, stderr=out)
        except SystemExit as exit_:
            self.fail(f"Pending model changes (exit {exit_.code}):\n{out.getvalue()}")
