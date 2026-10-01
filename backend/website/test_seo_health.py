"""The SEO health report (website.seo_health) and its endpoint: who may read
it, each check on crafted HTML, the override effect, the sitemap diff, the
company pages and the site-wide settings."""
import io
import tempfile
from pathlib import Path
from unittest import mock

from django.core.cache import cache
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import User
from org.models import Company
from website import seo_health
from website.models import SeoPageOverride, SeoSettings, Website

ORIGIN = "https://vezano.app"
GOOD_TITLE = "Pricing — clear plans for every store"  # 38 chars
GOOD_DESCRIPTION = (
    "Plans for stores and companies with clear prices and no per-transaction fees at all."
)


def page_html(
    url_path="/pricing/", *, title=GOOD_TITLE, description=GOOD_DESCRIPTION, canonical=None,
    hreflang=("ar", "en"), h1=1, og_image=True, json_ld=('{"@type": "WebPage"}',),
    robots="index, follow",
):
    """A page shaped like the Next export's: metadata in the head, the h1
    and JSON-LD in the body."""
    english = url_path.startswith("/en/")
    base = url_path[3:] if english else url_path
    head = ['<meta charSet="utf-8"/>']
    if title is not None:
        head.append(f"<title>{title}</title>")
    if description is not None:
        head.append(f'<meta name="description" content="{description}"/>')
    if robots:
        head.append(f'<meta name="robots" content="{robots}"/>')
    canonical = ORIGIN + url_path if canonical is None else canonical
    if canonical:
        head.append(f'<link rel="canonical" href="{canonical}"/>')
    for code in hreflang:
        href = ORIGIN + (f"/en{base}" if code == "en" else base)
        head.append(f'<link rel="alternate" hrefLang="{code}" href="{href}"/>')
    if og_image:
        head.append(f'<meta property="og:image" content="{ORIGIN}/marketing/og.png"/>')
    body = ['<svg><title>an icon, not the page title</title></svg>']
    body += ["<h1>Heading</h1>"] * h1
    body += [f'<script type="application/ld+json">{block}</script>' for block in json_ld]
    lang = "en" if english else "ar"
    return f'<!DOCTYPE html><html lang="{lang}"><head>{"".join(head)}</head><body>' \
        f'{"".join(body)}</body></html>'


def sitemap_xml(paths):
    urls = "".join(f"<url><loc>{ORIGIN}{path}</loc></url>" for path in paths)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        f'xmlns:xhtml="http://www.w3.org/1999/xhtml">{urls}</urlset>'
    )


ROBOTS = (
    "User-Agent: *\nAllow: /\nDisallow: /dashboard/\nDisallow: /login/\n\n"
    f"Host: {ORIGIN}\nSitemap: {ORIGIN}/sitemap.xml\nSitemap: {ORIGIN}/sitemap-sites.xml\n"
)


class ExportDir:
    """A throwaway frontend/out: {url path: html} plus robots and sitemap."""

    def __init__(self, testcase, pages, *, sitemap=None, robots=ROBOTS):
        self._tmp = tempfile.TemporaryDirectory()
        testcase.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name)
        for url_path, html in pages.items():
            target = self.path / url_path.strip("/") / "index.html"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(html, encoding="utf-8")
        (self.path / "404.html").write_text("<html><head></head></html>", encoding="utf-8")
        (self.path / "_next").mkdir()
        (self.path / "_next" / "x.html").write_text("<p>asset</p>", encoding="utf-8")
        if robots is not None:
            (self.path / "robots.txt").write_text(robots, encoding="utf-8")
        if sitemap is not None:
            (self.path / "sitemap.xml").write_text(sitemap_xml(sitemap), encoding="utf-8")


def codes(row):
    return {item["code"] for item in row["issues"]}


class PageCheckTests(SimpleTestCase):
    """Each per-page check on its own crafted page."""

    def check(self, html, url_path="/pricing/", **kwargs):
        facts = seo_health.parse_page(html)
        return seo_health.page_issues(facts, url_path, origin=ORIGIN, **kwargs)

    def test_a_good_page_has_no_findings(self):
        effective, issues = self.check(page_html())
        self.assertEqual(issues, [])
        self.assertEqual(effective["title"], GOOD_TITLE)
        self.assertEqual(effective["h1_count"], 1)
        self.assertEqual(effective["hreflang"], ["ar", "en"])

    def test_title_length(self):
        _, issues = self.check(page_html(title="Short"))
        self.assertEqual(issues, [seo_health.issue("title_short", "warn", length=5, min=15)])
        _, issues = self.check(page_html(title="x" * 61))
        self.assertEqual(issues, [seo_health.issue("title_long", "warn", length=61, max=60)])
        _, issues = self.check(page_html(title=None))
        self.assertEqual([i["code"] for i in issues], ["title_missing"])
        self.assertEqual(issues[0]["severity"], "error")

    def test_svg_title_in_the_body_is_not_the_page_title(self):
        effective, issues = self.check(page_html(title=None))
        self.assertEqual(effective["title"], "")
        self.assertIn("title_missing", {i["code"] for i in issues})

    def test_description_length(self):
        _, issues = self.check(page_html(description="Too short."))
        self.assertEqual([i["code"] for i in issues], ["description_short"])
        _, issues = self.check(page_html(description="d" * 161))
        self.assertEqual([i["code"] for i in issues], ["description_long"])
        _, issues = self.check(page_html(description=None))
        self.assertEqual([i["code"] for i in issues], ["description_missing"])

    def test_canonical(self):
        _, issues = self.check(page_html(canonical=""))
        self.assertEqual([i["code"] for i in issues], ["canonical_missing"])
        _, issues = self.check(page_html(canonical="https://www.example.com/pricing/"))
        self.assertEqual(
            [(i["code"], i["severity"]) for i in issues], [("canonical_host", "error")]
        )
        _, issues = self.check(page_html(canonical=f"{ORIGIN}/product/"))
        self.assertEqual(
            [(i["code"], i["severity"]) for i in issues], [("canonical_other", "warn")]
        )

    def test_hreflang_pair(self):
        _, issues = self.check(page_html(hreflang=("ar",)))
        self.assertEqual(issues, [seo_health.issue("hreflang_missing", "error", languages=["en"])])

    def test_exactly_one_h1(self):
        _, issues = self.check(page_html(h1=0))
        self.assertEqual([(i["code"], i["severity"]) for i in issues], [("h1_missing", "error")])
        _, issues = self.check(page_html(h1=2))
        self.assertEqual([(i["code"], i["severity"]) for i in issues], [("h1_multiple", "warn")])

    def test_og_image_or_the_default_share_image(self):
        _, issues = self.check(page_html(og_image=False))
        self.assertEqual([i["code"] for i in issues], ["og_image_missing"])
        _, issues = self.check(page_html(og_image=False), default_og_image=True)
        self.assertEqual(issues, [])

    def test_json_ld_must_parse(self):
        _, issues = self.check(page_html(json_ld=('{"ok": 1}', "{broken")))
        self.assertEqual(
            issues, [seo_health.issue("jsonld_invalid", "error", count=1, total=2)]
        )
        _, issues = self.check(page_html(json_ld=()))
        self.assertEqual([(i["code"], i["severity"]) for i in issues], [("jsonld_missing", "warn")])

    def test_override_is_judged_after_it_applies(self):
        override = {"title": "Plans", "description": "", "noindex": True, "canonical": ""}
        effective, issues = self.check(page_html(), override=override)
        self.assertEqual(effective["title"], "Plans")
        self.assertEqual(effective["own_title"], GOOD_TITLE)
        # The description was blank in the override, so the page's own stays.
        self.assertEqual(effective["description"], GOOD_DESCRIPTION)
        self.assertEqual(
            {i["code"] for i in issues}, {"title_short", "override_noindex"}
        )
        fixed, issues = self.check(
            page_html(title="x" * 90), override={"title": GOOD_TITLE, "canonical": ""}
        )
        self.assertEqual(fixed["title"], GOOD_TITLE)
        self.assertEqual(issues, [])

    def test_robots_extra_sanity(self):
        issues = seo_health.robots_extra_issues(
            "# comment\nDisallow: /old/\nDisalow: /typo/\nDisallow: /\nDisallow: /pricing",
            ["/pricing/", "/product/"],
        )
        self.assertEqual(
            [(i["code"], i["severity"], i["params"]["line"]) for i in issues],
            [
                ("robots_extra_unknown", "warn", 3),
                ("robots_extra_blocks_all", "error", 4),
                ("robots_extra_blocks_pages", "error", 5),
            ],
        )
        self.assertEqual(seo_health.robots_extra_issues(""), [])

    def test_url_path_of_export_files(self):
        self.assertEqual(seo_health.url_path_of("index.html"), "/")
        self.assertEqual(seo_health.url_path_of("en/pricing/index.html"), "/en/pricing/")
        self.assertEqual(seo_health.url_path_of("terms.html"), "/terms/")


class ExportAndSitemapTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def report(self, export):
        return seo_health.build_report(dist=export.path)

    def test_app_routes_are_skipped_and_the_sitemap_is_diffed_both_ways(self):
        export = ExportDir(self, {
            "/": page_html("/"),
            "/en/": page_html("/en/"),
            "/pricing/": page_html("/pricing/"),
            "/guides/": page_html("/guides/"),
            # Disallowed in robots.txt: the signed-in app.
            "/dashboard/": page_html("/dashboard/", robots="noindex, nofollow"),
            # Not disallowed but noindex: also the app, skipped.
            "/platform-errors/": page_html("/platform-errors/", robots="noindex, nofollow"),
            # Listed in the sitemap yet noindex: that is the finding.
            "/product/": page_html("/product/", robots="noindex, nofollow"),
        }, sitemap=["/", "/en/", "/pricing/", "/product/", "/gone/"])
        report = self.report(export)
        paths = [page["url_path"] for page in report["pages"]]
        self.assertEqual(sorted(paths), ["/", "/en/", "/guides/", "/pricing/", "/product/"])
        sitemap = report["sitemap"]
        self.assertEqual(sitemap["url_count"], 5)
        self.assertEqual(sitemap["missing_from_sitemap"], ["/guides/"])
        self.assertEqual(sitemap["missing_from_export"], ["/gone/"])
        self.assertEqual(
            codes(sitemap), {"pages_not_in_sitemap", "sitemap_dead_urls"}
        )
        self.assertEqual(sitemap["severity"], "error")
        by_path = {page["url_path"]: page for page in report["pages"]}
        self.assertEqual(codes(by_path["/guides/"]), {"not_in_sitemap"})
        self.assertEqual(codes(by_path["/product/"]), {"noindex_in_sitemap"})
        self.assertEqual(by_path["/en/"]["language"], "en")
        self.assertEqual(by_path["/en/"]["path"], "/")
        self.assertEqual(codes(by_path["/pricing/"]), set())
        self.assertTrue(by_path["/pricing/"]["in_sitemap"])

    def test_robots_must_name_both_sitemaps(self):
        export = ExportDir(
            self, {"/": page_html("/")}, sitemap=["/"],
            robots=f"User-Agent: *\nSitemap: {ORIGIN}/sitemap.xml\n",
        )
        sitemap = self.report(export)["sitemap"]
        self.assertEqual(
            sitemap["issues"],
            [seo_health.issue("robots_sitemap_missing", "warn", sitemap="sitemap-sites.xml")],
        )

    def test_missing_export_is_one_error_not_a_crash(self):
        with tempfile.TemporaryDirectory() as empty:
            report = seo_health.build_report(dist=Path(empty))
        self.assertEqual(report["pages"], [])
        self.assertEqual(codes(report["sitemap"]), {"export_missing"})

    def test_override_applies_by_language_with_exact_row_winning(self):
        export = ExportDir(self, {
            "/": page_html("/"),
            "/pricing/": page_html("/pricing/"),
            "/en/pricing/": page_html("/en/pricing/"),
        }, sitemap=["/", "/pricing/", "/en/pricing/"])
        SeoPageOverride.objects.create(path="/pricing", language="both", title="Too short")
        SeoPageOverride.objects.create(
            path="/pricing", language="en", title="Pricing that fits a store of any size",
        )
        pages = {page["url_path"]: page for page in self.report(export)["pages"]}
        arabic, english = pages["/pricing/"], pages["/en/pricing/"]
        self.assertEqual(arabic["override"]["language"], "both")
        self.assertEqual(arabic["title"], "Too short")
        self.assertEqual(codes(arabic), {"title_short"})
        self.assertEqual(english["override"]["language"], "en")
        self.assertEqual(english["title"], "Pricing that fits a store of any size")
        self.assertEqual(codes(english), set())

    def test_noindex_override_is_not_reported_as_missing_from_sitemap(self):
        export = ExportDir(self, {"/": page_html("/"), "/old/": page_html("/old/")}, sitemap=["/"])
        SeoPageOverride.objects.create(path="/old", language="both", noindex=True)
        pages = {page["url_path"]: page for page in self.report(export)["pages"]}
        self.assertEqual(codes(pages["/old/"]), {"override_noindex"})

    def test_summary_counts_rows_by_severity_and_ranks_issues(self):
        export = ExportDir(self, {
            "/": page_html("/"),
            "/a/": page_html("/a/", h1=0),
            "/b/": page_html("/b/", title="x" * 70),
            "/c/": page_html("/c/", title="y" * 70),
        }, sitemap=["/", "/a/", "/b/", "/c/"])
        summary = self.report(export)["summary"]
        # 4 pages, the sitemap row, 5 settings rows; no company pages.
        self.assertEqual(summary["total"], 10)
        self.assertEqual(summary["error"], 1)
        # Two long titles + three unset settings (verification x2, share image).
        self.assertEqual(summary["warn"], 5)
        self.assertEqual(summary["ok"], 4)
        self.assertEqual(summary["issues"][0], {"code": "h1_missing", "severity": "error",
                                                "count": 1})
        self.assertEqual(summary["issues"][1], {"code": "title_long", "severity": "warn",
                                                "count": 2})


class SettingsAndCompanyTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.export = ExportDir(self, {"/": page_html("/")}, sitemap=["/"])

    def settings_rows(self):
        report = seo_health.build_report(dist=self.export.path)
        return {row["code"]: row for row in report["settings"]}, report

    def test_settings_checks(self):
        rows, _ = self.settings_rows()
        self.assertEqual(rows["google_verification"]["severity"], "warn")
        self.assertEqual(rows["bing_verification"]["severity"], "warn")
        self.assertEqual(rows["default_og_image"]["severity"], "warn")
        self.assertEqual(rows["robots_extra"]["severity"], "ok")
        self.assertEqual(rows["directory"]["severity"], "ok")
        row = SeoSettings.load()
        row.google_site_verification = "tok"
        row.bing_site_verification = "bing"
        row.robots_extra = "Disallow: /"
        row.save()
        SeoPageOverride.objects.create(path="/s", language="both", noindex=True)
        rows, _ = self.settings_rows()
        self.assertEqual(rows["google_verification"]["severity"], "ok")
        self.assertEqual(rows["bing_verification"]["severity"], "ok")
        self.assertEqual(codes(rows["robots_extra"]), {"robots_extra_blocks_all"})
        self.assertEqual(codes(rows["directory"]), {"directory_noindex"})

    def test_company_page_completeness(self):
        complete = Company.objects.create(name="Complete Co", is_demo=True)
        Website.objects.create(
            company=complete, is_published=True, business_name="Complete",
            tagline="Fresh goods daily", logo_url="https://cdn.example.com/logo.png",
            contact_phone="+249912345678", services="Delivery\nWholesale",
        )
        bare = Company.objects.create(name="Bare Co")
        Website.objects.create(company=bare, is_published=True, list_in_directory=False)
        hidden = Company.objects.create(name="Hidden Co")
        Website.objects.create(
            company=hidden, is_published=True, about_text="About us", contact_email="a@b.co",
        )
        SeoPageOverride.objects.create(path=f"/s/{hidden.slug}/", language="ar", noindex=True)
        draft = Company.objects.create(name="Draft Co")
        Website.objects.create(company=draft, is_published=False)
        inactive = Company.objects.create(name="Gone Co", is_active=False)
        Website.objects.create(company=inactive, is_published=True)

        _, report = self.settings_rows()
        rows = {row["slug"]: row for row in report["companies"]}
        self.assertEqual(set(rows), {complete.slug, bare.slug, hidden.slug})

        self.assertEqual(rows[complete.slug]["missing"], ["cover"])
        self.assertTrue(rows[complete.slug]["is_demo"])
        self.assertTrue(rows[complete.slug]["in_directory"])
        self.assertEqual(rows[complete.slug]["url"], f"{ORIGIN}/s/{complete.slug}/")

        self.assertEqual(
            rows[bare.slug]["missing"], ["logo", "description", "cover", "contact", "services"]
        )
        self.assertIn("company_not_listed", codes(rows[bare.slug]))
        self.assertFalse(rows[bare.slug]["in_directory"])
        self.assertFalse(rows[bare.slug]["is_demo"])

        self.assertTrue(rows[hidden.slug]["noindex"])
        self.assertFalse(rows[hidden.slug]["in_directory"])
        self.assertEqual(
            codes(rows[hidden.slug]),
            {"company_noindex", "company_logo_missing", "company_cover_missing",
             "company_services_missing"},
        )


class SeoHealthApiTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.export = ExportDir(self, {"/": page_html("/")}, sitemap=["/"])
        patcher = mock.patch("core.frontend.FRONTEND_DIST", self.export.path)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.url = reverse("platform-seo-health")
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

    def test_view_capability_reads_and_others_are_refused(self):
        agent = self._invite("Support Agent")  # platform.seo.view only
        billing = self._invite("Billing Reviewer")  # no SEO capability
        tenant = User.objects.create_user(
            "owner@tenant.test", "secure-password", company=Company.objects.create(name="T"),
        )
        self.client.force_authenticate(agent)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["pages"][0]["url_path"], "/")
        self.assertEqual(self.client.get(self.url, {"refresh": "1"}).status_code, 403)
        self.client.force_authenticate(billing)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.client.force_authenticate(tenant)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_cached_until_refresh_or_an_override_change(self):
        first = self.client.get(self.url)
        self.assertEqual(first.status_code, 200)
        self.assertFalse(first.data["cached"])
        self.assertEqual(first.data["pages"][0]["title"], GOOD_TITLE)
        # A page edited on disk is not re-read while the report is cached…
        (self.export.path / "index.html").write_text(page_html("/", h1=0), encoding="utf-8")
        second = self.client.get(self.url)
        self.assertTrue(second.data["cached"])
        self.assertEqual(second.data["generated_at"], first.data["generated_at"])
        self.assertEqual(second.data["pages"][0]["issues"], [])
        # …a manager's refresh recomputes it…
        marketing = self._invite("Marketing Manager")
        self.client.force_authenticate(marketing)
        fresh = self.client.get(self.url, {"refresh": "1"})
        self.assertEqual(fresh.status_code, 200)
        self.assertFalse(fresh.data["cached"])
        self.assertEqual(codes(fresh.data["pages"][0]), {"h1_missing"})
        # …and so does saving an override.
        self.assertTrue(self.client.get(self.url).data["cached"])
        created = self.client.post(
            reverse("platform-seo-override-list"),
            {"path": "/", "language": "ar", "title": "Home"}, format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        after = self.client.get(self.url)
        self.assertFalse(after.data["cached"])
        self.assertEqual(after.data["pages"][0]["title"], "Home")
        self.assertEqual(after.data["pages"][0]["override"]["id"], created.data["id"])


class NoMigrationsTests(TestCase):
    def test_models_match_the_migrations(self):
        """The health check is read-only; production auto-deploy refuses a
        release that carries a migration, so none may be pending."""
        out = io.StringIO()
        try:
            call_command("makemigrations", "--check", "--dry-run", stdout=out, stderr=out)
        except SystemExit as exit_:  # makemigrations --check exits 1 on changes
            self.fail(f"Pending model changes (exit {exit_.code}):\n{out.getvalue()}")
        self.assertIn("No changes detected", out.getvalue())
