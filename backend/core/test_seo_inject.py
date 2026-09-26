"""core.seo_inject rewrites a page's <head> from plain values, and leaves
a page alone when there is nothing to apply."""
from django.test import SimpleTestCase

from core.seo_inject import (
    PageSeo,
    SiteSeo,
    analytics_snippet,
    append_robots_extra,
    inject_seo,
    public_path_and_language,
)

# The shape Next's export produces: self-closing metas, attributes in this order.
PAGE = (
    '<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charSet="utf-8"/>'
    "<title>فيزانو برو | نظام إدارة المبيعات</title>"
    '<meta name="description" content="الوصف الأصلي"/>'
    '<meta name="robots" content="index, follow"/>'
    '<link rel="canonical" href="https://vezano.app/pricing/"/>'
    '<meta property="og:title" content="فيزانو برو | نظام إدارة المبيعات"/>'
    '<meta property="og:description" content="الوصف الأصلي"/>'
    '<meta property="og:url" content="https://vezano.app/pricing/"/>'
    '<meta property="og:image" content="https://vezano.app/marketing/og.png"/>'
    '<meta name="twitter:title" content="فيزانو برو | نظام إدارة المبيعات"/>'
    '<meta name="twitter:description" content="الوصف الأصلي"/>'
    '<script src="/_next/static/chunks/main.js" async=""></script>'
    "</head><body><h1>Body <title>not a title</title></h1></body></html>"
)


class InjectSeoTests(SimpleTestCase):
    def test_nothing_to_apply_returns_the_same_document(self):
        self.assertIs(inject_seo(PAGE), PAGE)
        self.assertIs(inject_seo(PAGE, SiteSeo(), PageSeo()), PAGE)
        self.assertIs(inject_seo(PAGE, SiteSeo(robots_extra="Disallow: /x"), PageSeo()), PAGE)

    def test_document_without_a_head_is_untouched(self):
        self.assertEqual(inject_seo("plain text", SiteSeo(analytics_id="G-1")), "plain text")

    def test_title_and_description_replace_every_copy(self):
        out = inject_seo(PAGE, page=PageSeo(title='الأسعار <"جديد">', description="وصف جديد"))
        self.assertIn("<title>الأسعار &lt;\"جديد\"&gt;</title>", out)
        self.assertIn('<meta property="og:title" content="الأسعار &lt;&quot;جديد&quot;&gt;"/>', out)
        self.assertIn(
            '<meta name="twitter:title" content="الأسعار &lt;&quot;جديد&quot;&gt;"/>', out
        )
        self.assertIn('<meta name="description" content="وصف جديد"/>', out)
        self.assertIn('<meta property="og:description" content="وصف جديد"/>', out)
        self.assertIn('<meta name="twitter:description" content="وصف جديد"/>', out)
        self.assertNotIn("الوصف الأصلي", out)
        self.assertNotIn("فيزانو برو | نظام", out)
        # The body is never touched, even where it contains a <title>.
        self.assertIn("<h1>Body <title>not a title</title></h1>", out)
        # Nothing else in the head moved.
        self.assertIn('<meta name="robots" content="index, follow"/>', out)
        self.assertIn('<script src="/_next/static/chunks/main.js" async=""></script>', out)

    def test_blank_fields_keep_the_page_values(self):
        out = inject_seo(PAGE, page=PageSeo(title="عنوان فقط"))
        self.assertIn('<meta name="description" content="الوصف الأصلي"/>', out)
        self.assertIn('<link rel="canonical" href="https://vezano.app/pricing/"/>', out)

    def test_noindex_and_canonical(self):
        out = inject_seo(PAGE, page=PageSeo(noindex=True, canonical="https://vezano.app/prices/"))
        self.assertIn('<meta name="robots" content="noindex, nofollow"/>', out)
        self.assertNotIn("index, follow\"", out)
        self.assertIn('<link rel="canonical" href="https://vezano.app/prices/"/>', out)
        self.assertIn('<meta property="og:url" content="https://vezano.app/prices/"/>', out)
        self.assertEqual(out.count("rel=\"canonical\""), 1)

    def test_missing_tags_are_added_inside_the_head(self):
        bare = "<html><head><title>x</title></head><body></body></html>"
        page = PageSeo(description="d", noindex=True, canonical="https://v.app/")
        out = inject_seo(bare, page=page)
        head = out[: out.index("</head>")]
        self.assertIn('<meta name="description" content="d"/>', head)
        self.assertIn('<meta name="robots" content="noindex, nofollow"/>', head)
        self.assertIn('<link rel="canonical" href="https://v.app/"/>', head)

    def test_site_wide_tags(self):
        site = SiteSeo(
            google_site_verification="goog-token", bing_site_verification="bing-token",
            analytics_id="G-ABC123", default_og_image_url="/media/public/seo/share.webp",
        )
        out = inject_seo(PAGE, site=site)
        head = out[: out.index("</head>")]
        self.assertIn('<meta name="google-site-verification" content="goog-token"/>', head)
        self.assertIn('<meta name="msvalidate.01" content="bing-token"/>', head)
        self.assertIn("googletagmanager.com/gtag/js?id=G-ABC123", head)
        self.assertIn("gtag('config',\"G-ABC123\")", head)
        # The page has its own share image; the default is not forced over it.
        self.assertEqual(out.count("og:image"), 1)
        self.assertIn('content="https://vezano.app/marketing/og.png"', out)

    def test_default_share_image_fills_a_page_without_one(self):
        bare = "<html><head><title>x</title></head><body></body></html>"
        image = "https://v.app/media/public/seo/a.webp"
        out = inject_seo(bare, site=SiteSeo(default_og_image_url=image))
        self.assertIn(f'<meta property="og:image" content="{image}"/>', out)
        self.assertIn(f'<meta name="twitter:image" content="{image}"/>', out)

    def test_existing_verification_tag_is_replaced_not_duplicated(self):
        old = '<meta name="google-site-verification" content="old"/>'
        page = PAGE.replace("<title>", old + "<title>", 1)
        out = inject_seo(page, site=SiteSeo(google_site_verification="new"))
        self.assertEqual(out.count("google-site-verification"), 1)
        self.assertIn('content="new"', out)
        self.assertNotIn('content="old"', out)

    def test_analytics_id_is_validated(self):
        self.assertEqual(analytics_snippet("G-1</script><script>alert(1)"), "")
        self.assertEqual(analytics_snippet(""), "")
        self.assertIn("G-OK", analytics_snippet("G-OK"))
        self.assertEqual(inject_seo(PAGE, site=SiteSeo(analytics_id="bad id")), PAGE)

    def test_idempotent(self):
        site = SiteSeo(google_site_verification="tok", analytics_id="G-1")
        page = PageSeo(title="t", description="d", noindex=True, canonical="https://v.app/")
        once = inject_seo(PAGE, site, page)
        self.assertEqual(inject_seo(once, site, page), once)


class RobotsAndPathTests(SimpleTestCase):
    def test_robots_extra_is_appended_once_with_a_blank_line(self):
        base = "User-Agent: *\nAllow: /\n"
        self.assertEqual(append_robots_extra(base, ""), base)
        self.assertEqual(append_robots_extra(base, "  \n"), base)
        self.assertEqual(
            append_robots_extra(base, "Disallow: /old/\nDisallow: /tmp/\n"),
            "User-Agent: *\nAllow: /\n\nDisallow: /old/\nDisallow: /tmp/\n",
        )

    def test_public_path_and_language(self):
        cases = {
            "": ("/", "ar"),
            "/": ("/", "ar"),
            "index.html": ("/", "ar"),
            "pricing": ("/pricing", "ar"),
            "pricing/": ("/pricing", "ar"),
            "pricing/index.html": ("/pricing", "ar"),
            "en": ("/", "en"),
            "en/": ("/", "en"),
            "en/index.html": ("/", "en"),
            "en/pricing/": ("/pricing", "en"),
            "en/solutions/offline-pos/index.html": ("/solutions/offline-pos", "en"),
            "english/": ("/english", "ar"),
            "404.html": ("/404", "ar"),
        }
        for url_path, expected in cases.items():
            self.assertEqual(public_path_and_language(url_path), expected, url_path)
