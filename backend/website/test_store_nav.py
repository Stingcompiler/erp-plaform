"""The phone tab bar of a company's public pages.

Below 768px the header links are hidden, so the bar must carry every place
the header offers: home, products, the order (when the page takes orders),
tracking and contact, with a «المزيد» sheet for the rest; at most five
tabs; the tracking page marks its tab current."""

import re
from decimal import Decimal

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase

from inventory.models import Product, StockMovement, Warehouse
from org.models import Branch, Company
from website.models import FeaturedProduct, Website
from website.store_nav import MAX_TABS, mobile_nav


def bar(html):
    """(tab keys in the bar, «more» sheet keys, the bar's markup)."""
    nav = html.split('<nav class="tabbar"', 1)[1].split("</nav>", 1)[0]
    sheet = html.split('<div class="tb-sheet"', 1)[1].split("</div>", 1)[0] \
        if '<div class="tb-sheet"' in html else ""
    return re.findall(r'data-tab="(\w+)"', nav), re.findall(r'data-tab="(\w+)"', sheet), nav


def tab(nav, key):
    return re.search(r'<a [^>]*data-tab="%s"[^>]*>' % key, nav).group(0)


class PublicPagesTabBarTests(TestCase):
    def setUp(self):
        cache.clear()
        self.company = Company.objects.create(name="Bakery", slug="bakery", currency="SDG")
        branch = Branch.objects.create(company=self.company, name="Main")
        warehouse = Warehouse.objects.create(company=self.company, branch=branch, name="WH")
        self.site = Website.objects.create(
            company=self.company, business_name="مخبز النيل", is_published=True,
            accept_orders=True, contact_phone="+249900000000", about_text="نخبز كل صباح",
        )
        bread = Product.objects.create(
            company=self.company, sku="BR", name="Bread", sale_price=Decimal("500"),
            is_stock_tracked=True,
        )
        StockMovement.objects.create(
            company=self.company, product=bread, warehouse=warehouse,
            quantity=Decimal("10"), movement_type="adjustment",
        )
        FeaturedProduct.objects.create(company=self.company, website=self.site, product=bread)

    def test_store_taking_orders_gets_home_products_order_track_and_more(self):
        html = self.client.get("/s/bakery/").content.decode()
        tabs, more, nav = bar(html)
        self.assertEqual(tabs, ["home", "products", "order", "track", "more"])
        self.assertIn('aria-label="التنقل في الصفحة"', nav)
        self.assertIn('href="/s/bakery/track/"', tab(nav, "track"))
        self.assertIn('aria-current="location"', tab(nav, "home"))
        # The cart count rides on the order tab; it leads to products until
        # something is in the cart.
        self.assertIn('id="tb-cart-count"', nav)
        self.assertIn('href="#products"', tab(nav, "order"))
        self.assertIn('aria-expanded="false"', nav)
        # No room for a contact tab: WhatsApp, the call and the contact block
        # head the sheet, then the about section.
        self.assertEqual(more, ["whatsapp", "call", "about", "reach"])
        self.assertIn('href="https://wa.me/249900000000"', html)
        # The old floating WhatsApp button is gone (it sat where the bar is).
        self.assertNotIn('<a class="fab" ', html)
        self.assertIn("viewport-fit=cover", html)

    def test_store_without_ordering_gets_a_contact_tab(self):
        self.site.accept_orders = False
        self.site.save()
        html = self.client.get("/s/bakery/").content.decode()
        tabs, more, nav = bar(html)
        self.assertEqual(tabs, ["home", "products", "contact", "more"])
        self.assertIn('href="https://wa.me/249900000000"', tab(nav, "contact"))
        self.assertNotIn("tb-cart-count", html)
        self.assertEqual(more, ["about", "reach"])

    def test_page_with_nothing_but_contact(self):
        FeaturedProduct.objects.all().delete()
        self.site.accept_orders = False
        self.site.contact_phone = ""
        self.site.about_text = ""
        self.site.save()
        html = self.client.get("/s/bakery/").content.decode()
        tabs, more, nav = bar(html)
        self.assertEqual(tabs, ["home", "contact"])
        self.assertIn('href="#contact"', tab(nav, "contact"))
        self.assertEqual(more, [])
        self.assertNotIn('id="tb-more-btn"', html)

    def test_track_page_marks_the_track_tab_current(self):
        html = self.client.get("/s/bakery/track/").content.decode()
        tabs, more, nav = bar(html)
        self.assertEqual(tabs, ["home", "products", "track", "contact"])
        self.assertIn('aria-current="page"', tab(nav, "track"))
        self.assertIn('href="/s/bakery/track/"', tab(nav, "track"))
        self.assertEqual(nav.count("aria-current"), 1)
        self.assertIn('href="/s/bakery/"', tab(nav, "home"))
        self.assertIn('href="/s/bakery/#products"', tab(nav, "products"))
        self.assertIn("viewport-fit=cover", html)

    def test_pay_page_has_the_bar_too(self):
        html = self.client.get("/s/bakery/pay/?ref=X").content.decode()
        tabs, _, nav = bar(html)
        self.assertEqual(tabs, ["home", "products", "track", "contact"])
        self.assertNotIn("aria-current", nav)

    def test_english_page_labels(self):
        self.site.business_name = "Nile Bakery"
        self.site.about_text = "We bake every morning"
        self.site.save()
        html = self.client.get("/s/bakery/track/").content.decode()
        _, _, nav = bar(html)
        self.assertIn('aria-label="Page navigation"', nav)
        self.assertIn(">Track<", nav)


class MobileNavTests(SimpleTestCase):
    def test_never_more_than_five_tabs(self):
        nav = mobile_nav(
            "ar", page="site", site_path="/s/x/", track_path="/s/x/track/", products=True,
            accept_orders=True, whatsapp="249900000000", phone="+249900000000",
            about=True, gallery=True,
        )
        self.assertLessEqual(len(nav["tabs"]) + (1 if nav["more"] else 0), MAX_TABS)
        self.assertEqual(
            [item["key"] for item in nav["more"]],
            ["whatsapp", "call", "about", "gallery", "reach"],
        )

    def test_services_stand_in_for_products(self):
        nav = mobile_nav("en", page="site", site_path="/s/x/", services=True, phone="0912")
        self.assertEqual([t["key"] for t in nav["tabs"]], ["home", "services", "contact"])
        self.assertEqual(nav["tabs"][1]["href"], "#services")
        self.assertEqual(nav["tabs"][2]["href"], "tel:0912")
