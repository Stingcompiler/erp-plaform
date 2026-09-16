from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Role, User
from inventory.models import Product
from org.models import Branch, Company
from website.models import FeaturedProduct, Section, Website


class WebsiteBase(APITestCase):
    def setUp(self):
        self.company_a = Company.objects.create(name="Alpha Store")
        self.company_b = Company.objects.create(name="Beta Store")
        self.lpm_role = Role.objects.create(
            name="Landing Page Manager", scope_level=Role.SCOPE_BRANCH
        )
        self.sales_role = Role.objects.create(
            name="Sales Officer", scope_level=Role.SCOPE_BRANCH
        )
        self.branch_a = Branch.objects.create(company=self.company_a, name="Alpha branch")
        self.manager = User.objects.create_user(
            email="lpm@alpha.test", password="passw0rd123",
            company=self.company_a, role=self.lpm_role, branch=self.branch_a,
        )
        self.product = Product.objects.create(
            company=self.company_a, sku="SKU1", name="Nice Widget",
            sale_price=Decimal("25.00"), cost_price=Decimal("9.00"),
        )

    def login(self, email):
        c = self.client_class()
        r = c.post(reverse("auth-login"), {"email": email, "password": "passw0rd123"})
        assert r.status_code == 200, r.content
        return c


class EditAccessTests(WebsiteBase):
    def test_landing_page_manager_can_create_and_edit(self):
        c = self.login("lpm@alpha.test")
        # First GET auto-generates the site + default sections.
        resp = c.get(reverse("website-page"))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Section.objects.filter(company=self.company_a).exists())
        # Edit content.
        resp = c.patch(
            reverse("website-page"), {"tagline": "Best deals in town"}, format="json"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["tagline"], "Best deals in town")

    def test_non_website_role_cannot_edit(self):
        User.objects.create_user(
            email="sales@alpha.test", password="passw0rd123",
            company=self.company_a, role=self.sales_role, branch=self.branch_a,
        )
        c = self.login("sales@alpha.test")
        self.assertEqual(
            c.get(reverse("website-page")).status_code, status.HTTP_403_FORBIDDEN
        )


class PublicSiteTests(WebsiteBase):
    def _build_and_publish(self):
        c = self.login("lpm@alpha.test")
        c.get(reverse("website-page"))  # auto-generate
        site = Website.objects.get(company=self.company_a)
        FeaturedProduct.objects.create(
            company=self.company_a, website=site, product=self.product, order=0,
        )
        c.post(reverse("website-publish"), {"publish": True}, format="json")
        return c

    def test_public_site_served_by_slug_without_auth(self):
        self._build_and_publish()
        # Fresh client, no login.
        anon = self.client_class()
        resp = anon.get(reverse("public-site", args=[self.company_a.slug]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["business_name"], "Alpha Store")
        self.assertTrue(len(resp.data["sections"]) >= 1)

    def test_public_featured_products_expose_only_safe_fields(self):
        self._build_and_publish()
        anon = self.client_class()
        resp = anon.get(reverse("public-site", args=[self.company_a.slug]))
        fp = resp.data["featured_products"][0]
        self.assertEqual(fp["name"], "Nice Widget")
        self.assertEqual(Decimal(str(fp["price"])), Decimal("25.00"))
        # Internal fields must NOT leak.
        self.assertNotIn("cost_price", fp)
        self.assertNotIn("reorder_level", fp)

    def test_unpublished_site_is_404(self):
        c = self.login("lpm@alpha.test")
        c.get(reverse("website-page"))  # created but not published
        anon = self.client_class()
        resp = anon.get(reverse("public-site", args=[self.company_a.slug]))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_unknown_slug_is_404(self):
        anon = self.client_class()
        resp = anon.get(reverse("public-site", args=["does-not-exist"]))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_public_site_only_shows_visible_sections(self):
        self._build_and_publish()
        site = Website.objects.get(company=self.company_a)
        # Hide one section.
        sec = site.sections.first()
        sec.is_visible = False
        sec.save(update_fields=["is_visible"])
        anon = self.client_class()
        resp = anon.get(reverse("public-site", args=[self.company_a.slug]))
        types_shown = {s["type"] for s in resp.data["sections"]}
        self.assertNotIn(sec.type, types_shown | set())  # hidden one excluded
        self.assertTrue(all(s for s in resp.data["sections"]))

    def test_slug_isolation_between_companies(self):
        self._build_and_publish()  # company A published
        anon = self.client_class()
        # Company B has no published site.
        resp = anon.get(reverse("public-site", args=[self.company_b.slug]))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class PublicCompanyPageTests(PublicSiteTests):
    """The HTML page, directory and sitemap rendered for a published site."""

    def _publish_with_content(self):
        client = self._build_and_publish()
        site = Website.objects.get(company=self.company_a)
        site.tagline = "أفضل الأسعار في الخرطوم"
        site.about_text = 'نبيع كل شيء <script>alert("x")</script> بجودة'
        site.contact_phone = "+249 91 234 5678"
        site.primary_color = "#0e7c86"
        site.social_links = {"facebook": "https://facebook.com/alpha", "bad": "javascript:alert(1)"}
        site.save()
        Section.objects.create(
            company=self.company_a, website=site, type=Section.CONTACT, title="", order=9,
            content={"text": "زورونا في السوق"},
        )
        return client, site

    def test_published_site_renders_indexable_html(self):
        _, site = self._publish_with_content()
        response = self.client_class().get(reverse("public-site-page", args=[self.company_a.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/html; charset=utf-8")
        self.assertIn("max-age=300", response["Cache-Control"])
        html = response.content.decode()
        self.assertIn('<html lang="ar" dir="rtl">', html)
        self.assertIn("<title>Alpha Store — أفضل الأسعار في الخرطوم</title>", html)
        self.assertIn(
            f'<link rel="canonical" href="https://vezano.app/s/{self.company_a.slug}/">', html
        )
        self.assertIn('<meta name="robots" content="index, follow">', html)
        self.assertIn('"@type": "LocalBusiness"', html)
        self.assertIn('"telephone": "+249 91 234 5678"', html)
        self.assertIn('"@type": "Product"', html)
        self.assertIn('"name": "Nice Widget"', html)
        self.assertIn("--accent:#0e7c86", html)
        self.assertIn('href="https://wa.me/249912345678"', html)
        self.assertIn('href="https://facebook.com/alpha"', html)
        self.assertNotIn("javascript:alert", html)
        # Merchant text is escaped, never executed.
        self.assertNotIn('<script>alert("x")</script>', html)
        self.assertIn("&lt;script&gt;", html)
        # Nothing internal.
        self.assertNotIn("cost_price", html)
        self.assertNotIn("reorder_level", html)

    def test_english_content_renders_ltr(self):
        self._build_and_publish()
        site = Website.objects.get(company=self.company_a)
        site.tagline = "Best prices in town"
        site.save()
        html = self.client_class().get(
            reverse("public-site-page", args=[self.company_a.slug])
        ).content.decode()
        self.assertIn('<html lang="en" dir="ltr">', html)

    def test_unpublished_or_unknown_site_is_404(self):
        client = self.login("lpm@alpha.test")
        client.get(reverse("website-page"))
        anon = self.client_class()
        own = anon.get(reverse("public-site-page", args=[self.company_a.slug]))
        self.assertEqual(own.status_code, 404)
        self.assertEqual(anon.get(reverse("public-site-page", args=["nope"])).status_code, 404)

    def test_invalid_colour_falls_back(self):
        _, site = self._publish_with_content()
        site.primary_color = "red;}</style><script>x</script>"
        site.save()
        html = self.client_class().get(
            reverse("public-site-page", args=[self.company_a.slug])
        ).content.decode()
        self.assertIn("--accent:#111827", html)
        self.assertNotIn("<script>x</script>", html)

    def test_directory_and_sitemap_list_published_sites_only(self):
        self._publish_with_content()
        anon = self.client_class()
        directory = anon.get(reverse("public-site-directory"))
        self.assertEqual(directory.status_code, 200)
        self.assertIn(f'href="/s/{self.company_a.slug}/"', directory.content.decode())
        sitemap = anon.get(reverse("public-sites-sitemap"))
        self.assertEqual(sitemap.status_code, 200)
        self.assertEqual(sitemap["Content-Type"], "application/xml; charset=utf-8")
        body = sitemap.content.decode()
        self.assertIn(f"<loc>https://vezano.app/s/{self.company_a.slug}/</loc>", body)
        self.assertIn("<loc>https://vezano.app/s/</loc>", body)
        Website.objects.filter(company=self.company_a).update(is_published=False)
        self.assertNotIn(
            self.company_a.slug, anon.get(reverse("public-sites-sitemap")).content.decode()
        )
        self.assertNotIn(
            f'href="/s/{self.company_a.slug}/"',
            anon.get(reverse("public-site-directory")).content.decode(),
        )
