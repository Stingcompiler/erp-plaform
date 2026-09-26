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
        r = c.post(reverse("auth-login"), {
            "email": email,
            "password": "passw0rd123",
            "device_id": "TEST",
        })
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

    def test_demo_company_is_labelled_and_vezano_in_the_top_strip_and_footer(self):
        self._publish_with_content()
        anon = self.client_class()
        url = reverse("public-site-page", args=[self.company_a.slug])
        html = anon.get(url).content.decode()
        # A real customer: no demo label. Vezano appears twice: the slim
        # "back to Vezano Pro" strip at the top (owner, 2026-09-26) and the
        # "powered by" line in the footer — nowhere in the company's content.
        self.assertNotIn("شركة تجريبية لاستكشاف النظام", html)
        self.assertIn("مدعوم من <a", html)
        self.assertIn('<div class="vz-strip"', html)
        self.assertEqual(html.count("فيزانو"), 2)
        # The platform wordmark «فيزانو برو», in Readex Pro for that line only.
        self.assertIn('فيزانو <span class="pro">برو</span></a>', html)
        self.assertIn("family=Readex+Pro", html)
        self.assertIn("family=Tajawal", html)
        self.assertNotIn("Cairo", html)
        self.company_a.is_demo = True
        self.company_a.save(update_fields=["is_demo"])
        html = anon.get(url).content.decode()
        self.assertIn('<p class="demo-note" role="note">شركة تجريبية لاستكشاف النظام</p>', html)
        directory = anon.get(reverse("public-site-directory")).content.decode()
        self.assertIn('<p class="demo">شركة تجريبية لاستكشاف النظام</p>', directory)
        # The directory header carries the platform logo mark and wordmark.
        self.assertIn('<svg class="vz-mark" aria-hidden="true"', directory)
        self.assertNotIn('<span class="mark">V</span>', directory)
        self.assertIn('فيزانو <span class="pro">برو</span>', directory)

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
        # The field is 16 characters wide (Postgres enforces it), which is
        # still enough to try to break out of the stylesheet.
        site.primary_color = "x;}</style><b>"
        site.save()
        html = self.client_class().get(
            reverse("public-site-page", args=[self.company_a.slug])
        ).content.decode()
        self.assertIn("--accent:#111827", html)
        self.assertNotIn("</style><b>", html)

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


def _png(width=1200, height=800, colour=(14, 124, 134)):
    """A real PNG in memory, so the upload path exercises Pillow."""
    import io

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (width, height), colour).save(buffer, format="PNG")
    return SimpleUploadedFile("photo.png", buffer.getvalue(), content_type="image/png")


class LandingPageImageTests(PublicSiteTests):
    """Uploads for cover, logo, gallery and product photos; the public
    media route; the landing page and JSON-LD that use them."""

    def setUp(self):
        import tempfile

        from django.test import override_settings

        super().setUp()
        self._media = tempfile.TemporaryDirectory()
        self._override = override_settings(MEDIA_ROOT=self._media.name)
        self._override.enable()
        self.addCleanup(self._override.disable)
        self.addCleanup(self._media.cleanup)

    def test_cover_and_logo_upload_are_resized_webp_and_served_publicly(self):
        client = self._build_and_publish()
        cover = client.post(
            reverse("website-image", args=["cover"]), {"image": _png(3000, 2000)},
            format="multipart",
        )
        self.assertEqual(cover.status_code, 200, cover.data)
        self.assertTrue(cover.data["cover_image_url"].startswith("/media/public/"))
        self.assertTrue(cover.data["cover_image_url"].endswith(".webp"))
        logo = client.post(
            reverse("website-image", args=["logo"]), {"image": _png(900, 300)},
            format="multipart",
        )
        self.assertEqual(logo.status_code, 200, logo.data)
        site = Website.objects.get(company=self.company_a)
        from PIL import Image

        with Image.open(site.cover_image.path) as image:
            self.assertEqual(image.format, "WEBP")
            self.assertLessEqual(max(image.size), 1800)
        with Image.open(site.logo_image.path) as image:
            self.assertEqual(image.size, (512, 512))
        # Served to anyone, cacheable for a year; nothing outside public/ is.
        anon = self.client_class()
        path = site.cover_image.name.split("public/", 1)[1]
        served = anon.get(reverse("public-media", args=[path]))
        self.assertEqual(served.status_code, 200)
        self.assertEqual(served["Content-Type"], "image/webp")
        self.assertIn("immutable", served["Cache-Control"])
        # Traversal is refused (Django answers 400 for a suspicious path).
        self.assertIn(anon.get("/media/public/../secret.webp").status_code, (400, 404))
        self.assertEqual(anon.get(reverse("public-media", args=["nope.webp"])).status_code, 404)
        # Replacing deletes the old file; removing clears the field.
        old_path = site.cover_image.path
        client.post(
            reverse("website-image", args=["cover"]), {"image": _png()}, format="multipart"
        )
        import os

        self.assertFalse(os.path.exists(old_path))
        removed = client.delete(reverse("website-image", args=["cover"]))
        self.assertEqual(removed.status_code, 200)
        self.assertEqual(removed.data["cover_image_url"], "")

    def test_rejects_non_images_and_oversized_files(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        client = self._build_and_publish()
        fake = SimpleUploadedFile("x.png", b"<html>not an image</html>", content_type="image/png")
        bad = client.post(
            reverse("website-image", args=["cover"]), {"image": fake}, format="multipart"
        )
        self.assertEqual(bad.status_code, 400)
        huge = SimpleUploadedFile("big.png", b"0" * (8 * 1024 * 1024 + 1), content_type="image/png")
        big = client.post(
            reverse("website-image", args=["cover"]), {"image": huge}, format="multipart"
        )
        self.assertEqual(big.status_code, 400)
        missing = client.post(reverse("website-image", args=["cover"]), {}, format="multipart")
        self.assertEqual(missing.status_code, 400)

    def test_gallery_and_product_photos_reach_the_landing_page(self):
        client = self._build_and_publish()
        photo = client.post(
            reverse("website-image-list"), {"image": _png(800, 800), "caption": "الواجهة"},
            format="multipart",
        )
        self.assertEqual(photo.status_code, 201, photo.data)
        self.assertEqual(photo.data["company"], self.company_a.id)
        # A product photo is inventory data: the website role alone may not
        # set it (403); an owner may.
        refused = client.post(
            reverse("product-image", args=[self.product.id]), {"image": _png(600, 400)},
            format="multipart",
        )
        self.assertEqual(refused.status_code, 403)
        owner_role = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123",
            company=self.company_a, role=owner_role, branch=self.branch_a,
        )
        owner = self.login("owner@alpha.test")
        product_image = owner.post(
            reverse("product-image", args=[self.product.id]), {"image": _png(600, 400)},
            format="multipart",
        )
        self.assertEqual(product_image.status_code, 200, product_image.data)
        self.assertTrue(product_image.data["image_url"].endswith(".webp"))
        client.patch(
            reverse("website-page"),
            {"opening_hours": "السبت - الخميس 8ص - 10م\nالجمعة مغلق", "city": "الخرطوم",
             "category": "grocery", "map_url": "https://maps.google.com/?q=x"},
            format="json",
        )
        page = self.client_class().get(reverse("public-site-page", args=[self.company_a.slug]))
        html = page.content.decode()
        self.assertIn('id="gallery"', html)
        # The page carries absolute URLs for crawlers; the API relative ones.
        self.assertIn("https://vezano.app" + photo.data["url"], html)
        self.assertIn("https://vezano.app" + product_image.data["image_url"], html)
        self.assertIn("السبت - الخميس 8ص - 10م", html)
        self.assertIn('"openingHours": ["السبت - الخميس 8ص - 10م", "الجمعة مغلق"]', html)
        self.assertIn('"addressLocality": "الخرطوم"', html)
        self.assertIn('"hasMap": "https://maps.google.com/?q=x"', html)
        self.assertIn('"image": "https://vezano.app' + product_image.data["image_url"], html)
        # The JSON endpoint gained the new fields without losing the old ones.
        data = self.client_class().get(reverse("public-site", args=[self.company_a.slug])).data
        for key in ("business_name", "sections", "featured_products", "gallery", "opening_hours"):
            self.assertIn(key, data)
        self.assertEqual(data["gallery"][0]["caption"], "الواجهة")
        # Removing a gallery photo deletes its file.
        import os

        stored = Website.objects.get(company=self.company_a).images.first()
        path = stored.image.path
        deleted = client.delete(reverse("website-image-detail", args=[stored.id]))
        self.assertEqual(deleted.status_code, 204)
        self.assertFalse(os.path.exists(path))

    def test_other_company_cannot_touch_my_gallery(self):
        client = self._build_and_publish()
        photo = client.post(
            reverse("website-image-list"), {"image": _png(400, 400)}, format="multipart"
        )
        User.objects.create_user(
            email="lpm@beta.test", password="passw0rd123",
            company=self.company_b, role=self.lpm_role,
            branch=Branch.objects.create(company=self.company_b, name="Beta branch"),
        )
        other = self.login("lpm@beta.test")
        gone = other.delete(reverse("website-image-detail", args=[photo.data["id"]]))
        self.assertEqual(gone.status_code, 404)
        listed = other.get(reverse("website-image-list")).data
        rows = listed["results"] if isinstance(listed, dict) else listed
        self.assertEqual(len(rows), 0)

    def test_opted_out_site_is_reachable_but_unlisted(self):
        self._build_and_publish()
        Website.objects.filter(company=self.company_a).update(list_in_directory=False)
        anon = self.client_class()
        page = anon.get(reverse("public-site-page", args=[self.company_a.slug]))
        self.assertEqual(page.status_code, 200)
        sitemap = anon.get(reverse("public-sites-sitemap")).content.decode()
        self.assertNotIn(self.company_a.slug, sitemap)
        directory = anon.get(reverse("public-site-directory")).content.decode()
        self.assertNotIn(f"/s/{self.company_a.slug}/", directory)

    def test_services_are_validated_listed_and_shown_on_the_page(self):
        client = self._build_and_publish()
        page = client.get(reverse("website-page")).data
        self.assertIn("services", page["missing"])
        too_long = client.patch(
            reverse("website-page"), {"services": "x" * 61}, format="json"
        )
        self.assertEqual(too_long.status_code, 400)
        saved = client.patch(
            reverse("website-page"),
            {"services": " توصيل \n\nصيانة\nتركيب\nضمان\nتقسيط\nاستبدال\nسابع مهمل"},
            format="json",
        )
        self.assertEqual(saved.status_code, 200, saved.data)
        self.assertEqual(saved.data["services"], "توصيل\nصيانة\nتركيب\nضمان\nتقسيط\nاستبدال")
        self.assertNotIn("services", saved.data["missing"])
        public = self.client_class().get(reverse("public-site", args=[self.company_a.slug])).data
        self.assertEqual(
            public["services"], ["توصيل", "صيانة", "تركيب", "ضمان", "تقسيط", "استبدال"]
        )
        html = self.client_class().get(
            reverse("public-site-page", args=[self.company_a.slug])
        ).content.decode()
        self.assertIn('<div class="services" id="services">', html)
        self.assertIn('<span class="item">توصيل</span>', html)
        self.assertNotIn("سابع مهمل", html)
        directory = self.client_class().get(reverse("public-site-directory")).content.decode()
        self.assertIn(
            '<span>توصيل</span><span>صيانة</span><span>تركيب</span><span class="more">+3</span>',
            directory,
        )

    def test_missing_items_guide_the_merchant(self):
        client = self._build_and_publish()
        data = client.get(reverse("website-page")).data
        for item in ("cover_image", "logo", "tagline", "category", "product_with_image"):
            self.assertIn(item, data["missing"])
        client.post(reverse("website-image", args=["cover"]), {"image": _png()}, format="multipart")
        data = client.get(reverse("website-page")).data
        self.assertNotIn("cover_image", data["missing"])


class PreviewAndShowcaseTests(LandingPageImageTests):
    """The owner's draft preview, the showcase feed and the card directory."""

    def _complete(self, client):
        for kind, image in (("cover", _png()), ("logo", _png(500, 500))):
            client.post(reverse("website-image", args=[kind]), {"image": image}, format="multipart")
        owner_role = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123",
            company=self.company_a, role=owner_role, branch=self.branch_a,
        )
        self.login("owner@alpha.test").post(
            reverse("product-image", args=[self.product.id]), {"image": _png(600, 400)},
            format="multipart",
        )
        client.patch(
            reverse("website-page"),
            {"tagline": "أفضل الأسعار", "about_text": "نبذة", "contact_phone": "0912345678",
             "category": "grocery", "city": "الخرطوم",
             "services": "توصيل للمنازل\nبيع بالجملة\n\nتقسيط"},
            format="json",
        )

    def test_owner_previews_an_unpublished_draft(self):
        client = self.login("lpm@alpha.test")
        client.get(reverse("website-page"))  # created, not published
        anon = self.client_class()
        self.assertEqual(anon.get(reverse("website-preview")).status_code, 401)
        preview = client.get(reverse("website-preview"))
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview["Cache-Control"], "no-store")
        self.assertEqual(preview["X-Robots-Tag"], "noindex")
        self.assertEqual(preview["X-Frame-Options"], "SAMEORIGIN")
        self.assertEqual(preview["Content-Security-Policy"], "frame-ancestors 'self'")
        html = preview.content.decode()
        self.assertIn('content="noindex, nofollow"', html)
        self.assertIn("Preview", html)  # English fixture; Arabic sites get "معاينة"
        # Still not public.
        hidden = anon.get(reverse("public-site-page", args=[self.company_a.slug]))
        self.assertEqual(hidden.status_code, 404)

    def test_showcase_lists_only_complete_listed_sites(self):
        client = self._build_and_publish()
        anon = self.client_class()
        self.assertEqual(anon.get(reverse("public-showcase")).json()["sites"], [])
        self._complete(client)
        sites = anon.get(reverse("public-showcase")).json()["sites"]
        self.assertEqual(len(sites), 1)
        card = sites[0]
        self.assertEqual(card["name"], "Alpha Store")
        self.assertEqual(card["url"], f"https://vezano.app/s/{self.company_a.slug}/")
        self.assertTrue(card["cover"].startswith("https://vezano.app/media/public/"))
        self.assertTrue(card["logo"].startswith("https://vezano.app/media/public/"))
        self.assertEqual(card["category_label"], "مواد غذائية")
        self.assertTrue(card["complete"])
        self.assertFalse(card["is_demo"])
        self.company_a.is_demo = True
        self.company_a.save(update_fields=["is_demo"])
        self.assertTrue(anon.get(reverse("public-showcase")).json()["sites"][0]["is_demo"])
        Website.objects.filter(company=self.company_a).update(list_in_directory=False)
        self.assertEqual(anon.get(reverse("public-showcase")).json()["sites"], [])

    def test_directory_shows_every_listed_site_as_a_card_and_filters_by_category(self):
        client = self._build_and_publish()
        anon = self.client_class()
        html = anon.get(reverse("public-site-directory")).content.decode()
        # An incomplete site still gets a card: placeholder cover, initial as
        # the logo, featured product names as what it offers, a visit button.
        self.assertIn('class="card"', html)
        self.assertIn('<span class="ph">Alpha Store</span>', html)
        self.assertIn('<span class="logo mark" aria-hidden="true">A</span>', html)
        self.assertIn('<div class="offers"><span>Nice Widget</span></div>', html)
        self.assertIn(f'<a class="go" href="/s/{self.company_a.slug}/">', html)
        self.assertNotIn('<ul class="plain">', html)
        self._complete(client)
        html = anon.get(reverse("public-site-directory")).content.decode()
        self.assertIn('class="card"', html)
        self.assertIn("مواد غذائية", html)
        # Real cover and logo replace the placeholders; the services list
        # replaces the product names (three shown, the rest counted).
        self.assertNotIn('class="ph"', html)
        self.assertNotIn('logo mark', html)
        self.assertIn('<img class="logo" src=', html)
        self.assertIn("<span>توصيل للمنازل</span><span>بيع بالجملة</span><span>تقسيط</span>", html)
        self.assertNotIn("Nice Widget", html)
        directory = reverse("public-site-directory")
        filtered = anon.get(directory + "?category=pharmacy").content.decode()
        self.assertNotIn('class="card"', filtered)
        self.assertNotIn(f'href="/s/{self.company_a.slug}/"', filtered)
        self.assertEqual(anon.get(directory + "?category=<x>").status_code, 200)
