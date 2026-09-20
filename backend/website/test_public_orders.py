"""Orders from the public page: the catalogue honours the owner's price and
order choices, a visitor's order lands with the branch it chose, the
branch is told, and confirming makes a customer and a sales order."""

from decimal import Decimal

from django.core import mail
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import Role, User
from inventory.models import Product
from org.models import Branch, Company
from sales.models import Customer, SalesOrder
from website.models import FeaturedProduct, PublicOrder, Website


@override_settings(
    EMAIL_ENABLED=True, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    PUBLIC_APP_ORIGIN="https://vezano.app",
)
class PublicOrderTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Bakery", slug="bakery", currency="SDG")
        self.main = Branch.objects.create(company=self.company, name="Main", phone="+249900000001")
        self.north = Branch.objects.create(
            company=self.company, name="North", phone="+249900000002"
        )
        owner_role = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        manager_role = Role.objects.create(name="Branch Manager", scope_level=Role.SCOPE_BRANCH)
        sales_role = Role.objects.create(name="Sales Officer", scope_level=Role.SCOPE_BRANCH)
        self.owner = User.objects.create_user(
            email="owner@bakery.test", password="Owner-passw0rd!x", company=self.company,
            role=owner_role, full_name="Owner",
        )
        self.north_manager = User.objects.create_user(
            email="north@bakery.test", password="Mgr-passw0rd!x", company=self.company,
            role=manager_role, branch=self.north, full_name="North Manager",
        )
        self.main_clerk = User.objects.create_user(
            email="clerk@bakery.test", password="Clerk-passw0rd!x", company=self.company,
            role=sales_role, branch=self.main,
        )
        self.site = Website.objects.create(
            company=self.company, business_name="Bakery", is_published=True,
            accept_orders=True, contact_phone="+249900000000",
        )
        self.bread = Product.objects.create(
            company=self.company, sku="BR", name="Bread", sale_price=Decimal("500"),
            is_stock_tracked=False,
        )
        self.cake = Product.objects.create(
            company=self.company, sku="CK", name="Cake", sale_price=Decimal("12000"),
            is_stock_tracked=True,
        )
        FeaturedProduct.objects.create(
            company=self.company, website=self.site, product=self.bread, show_price=True
        )
        FeaturedProduct.objects.create(
            company=self.company, website=self.site, product=self.cake, show_price=False
        )
        self.client = APIClient()

    def test_catalogue_honours_owner_choices_and_live_stock(self):
        response = self.client.get("/api/public/site/bakery/")
        self.assertEqual(response.status_code, 200)
        products = {p["sku"]: p for p in response.data["featured_products"]}
        self.assertEqual(products["BR"]["price"], "500.00")
        self.assertTrue(products["BR"]["in_stock"])
        self.assertIsNone(products["CK"]["price"])       # owner hid it
        self.assertFalse(products["CK"]["in_stock"])     # tracked, nothing on hand
        self.assertTrue(response.data["accept_orders"])

    def test_visitor_order_reaches_the_chosen_branch(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self._post_amal()
        self._assert_amal(response)

    def _post_amal(self):
        return self.client.post(
            "/api/public/site/bakery/orders/",
            {
                "contact_name": "Amal", "phone": "0912 345 678", "branch": self.north.pk,
                "delivery_mode": "delivery", "address": "شارع النيل 5", "note": "بعد الظهر",
                "language": "ar",
                "lines": [
                    {"product": self.bread.pk, "quantity": 3},
                    {"product": self.cake.pk, "quantity": 1},
                ],
            },
            format="json",
        )

    def _assert_amal(self, response):
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data["reference"].startswith("W"))
        self.assertEqual(response.data["whatsapp"], "249900000002")   # the branch's number
        order = PublicOrder.objects.get(reference=response.data["reference"])
        self.assertEqual(order.branch, self.north)
        self.assertEqual(order.phone, "0912345678")
        self.assertIsNone(order.total)  # one line has a hidden price
        lines = {line.name: line for line in order.lines.all()}
        self.assertEqual(lines["Bread"].unit_price, Decimal("500"))
        self.assertIsNone(lines["Cake"].unit_price)
        # Told: the branch manager, and the owner (the site's default).
        told = sorted(m.to[0] for m in mail.outbox)
        self.assertEqual(told, ["north@bakery.test", "owner@bakery.test"])
        self.assertIn(order.reference, mail.outbox[0].subject)
        self.assertIn("/web-orders/?ref=", mail.outbox[0].body)

    def test_no_branch_manager_means_the_owner_is_told(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                "/api/public/site/bakery/orders/",
                {"contact_name": "Amal", "phone": "0912345678", "branch": self.main.pk,
                 "lines": [{"product": self.bread.pk, "quantity": 1}]},
                format="json",
            )
        self.assertEqual([m.to for m in mail.outbox], [["owner@bakery.test"]])

    def test_refusals(self):
        one = [{"product": self.bread.pk, "quantity": 1}]
        bad = [
            ({"contact_name": "", "phone": "0912345678", "lines": one}, "contact_name"),
            ({"contact_name": "A", "phone": "12", "lines": one}, "phone"),
            ({"contact_name": "A", "phone": "0912345678", "lines": []}, "lines"),
            ({"contact_name": "A", "phone": "0912345678", "delivery_mode": "delivery",
              "lines": [{"product": self.bread.pk, "quantity": 1}]}, "address"),
        ]
        for payload, field in bad:
            response = self.client.post("/api/public/site/bakery/orders/", payload, format="json")
            self.assertEqual(response.status_code, 400, payload)
            self.assertIn(field, response.data)
        # A product the owner did not open for ordering.
        FeaturedProduct.objects.filter(product=self.cake).update(allow_order=False)
        response = self.client.post(
            "/api/public/site/bakery/orders/",
            {"contact_name": "A", "phone": "0912345678",
             "lines": [{"product": self.cake.pk, "quantity": 1}]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        # Honeypot filled: accepted, nothing stored.
        response = self.client.post(
            "/api/public/site/bakery/orders/",
            {"contact_name": "Bot", "phone": "0912345678", "website_url": "http://spam",
             "lines": [{"product": self.bread.pk, "quantity": 1}]},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(PublicOrder.objects.count(), 0)
        # Site not taking orders.
        self.site.accept_orders = False
        self.site.save()
        response = self.client.post(
            "/api/public/site/bakery/orders/",
            {"contact_name": "A", "phone": "0912345678",
             "lines": [{"product": self.bread.pk, "quantity": 1}]},
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    def _place(self, branch):
        return self.client.post(
            "/api/public/site/bakery/orders/",
            {"contact_name": "Amal", "phone": "0912345678", "branch": branch.pk,
             "lines": [{"product": self.bread.pk, "quantity": 2}]},
            format="json",
        ).data["reference"]

    def test_company_sees_scoped_orders_and_confirms_into_a_sales_order(self):
        ref_north = self._place(self.north)
        ref_main = self._place(self.main)
        clerk = APIClient()
        clerk.force_authenticate(self.main_clerk)
        listing = clerk.get("/api/web-orders/")
        refs = {row["reference"] for row in (listing.data.get("results") or listing.data)}
        self.assertEqual(refs, {ref_main})
        owner = APIClient()
        owner.force_authenticate(self.owner)
        listing = owner.get("/api/web-orders/?status=new")
        refs = {row["reference"] for row in (listing.data.get("results") or listing.data)}
        self.assertEqual(refs, {ref_main, ref_north})

        order = PublicOrder.objects.get(reference=ref_north)
        confirmed = owner.post(
            f"/api/web-orders/{order.pk}/confirm/", {"note": "ok"}, format="json"
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.data)
        self.assertEqual(confirmed.data["status"], "confirmed")
        customer = Customer.objects.get(company=self.company, phone="0912345678")
        self.assertEqual(customer.name, "Amal")
        sales_order = SalesOrder.objects.get(pk=confirmed.data["sales_order"])
        self.assertEqual(sales_order.status, SalesOrder.CONFIRMED)
        self.assertEqual(sales_order.branch, self.north)
        self.assertEqual(sales_order.customer, customer)
        self.assertEqual(sales_order.lines.get().quantity, Decimal("2"))
        self.assertEqual(sales_order.total, Decimal("1000.00"))
        # Answering twice is refused; the second order goes to the same customer.
        self.assertEqual(owner.post(f"/api/web-orders/{order.pk}/confirm/").status_code, 400)
        other = PublicOrder.objects.get(reference=ref_main)
        owner.post(f"/api/web-orders/{other.pk}/confirm/")
        self.assertEqual(Customer.objects.filter(company=self.company).count(), 1)

    def test_reject_with_reason(self):
        ref = self._place(self.main)
        order = PublicOrder.objects.get(reference=ref)
        owner = APIClient()
        owner.force_authenticate(self.owner)
        rejected = owner.post(f"/api/web-orders/{order.pk}/reject/", {"note": "نفد"}, format="json")
        self.assertEqual(rejected.data["status"], "rejected")
        self.assertEqual(rejected.data["decision_note"], "نفد")
        self.assertFalse(SalesOrder.objects.exists())

    def test_badge_counts_new_orders_for_the_branch(self):
        from django.utils import timezone
        from datetime import timedelta
        from website.attention import new_public_orders

        since = timezone.now() - timedelta(minutes=1)
        self._place(self.north)
        self._place(self.main)
        self.assertEqual(new_public_orders(self.owner, since), 2)
        self.assertEqual(new_public_orders(self.main_clerk, since), 1)


class PublicPageLayoutTests(PublicOrderTests):
    def test_order_form_honeypot_is_clipped_not_offscreen(self):
        """left:-9999px on an RTL page is scrollable overflow: after the first
        "add to order" the page became 10,000 px wide and the viewport slid
        sideways. The trap must hide by clipping, and the page must forbid
        sideways scroll."""
        html = self.client.get("/s/bakery/").content.decode()
        self.assertIn('name="website_url"', html)
        self.assertNotIn("-9999", html)
        self.assertIn(".order .hp{position:absolute;width:1px;height:1px", html)
        self.assertIn("overflow-x:clip", html)
        self.assertIn("focus({preventScroll:true})", html)
