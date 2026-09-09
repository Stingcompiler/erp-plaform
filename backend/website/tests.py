from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Role, User
from inventory.models import Product
from org.models import Company
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
        self.manager = User.objects.create_user(
            email="lpm@alpha.test", password="passw0rd123",
            company=self.company_a, role=self.lpm_role,
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
            company=self.company_a, role=self.sales_role,
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
