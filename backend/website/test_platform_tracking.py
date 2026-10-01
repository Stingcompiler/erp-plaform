"""vezano.app/track/ — POST /api/public/track/.

Web orders from every published store (labelled with the store, linked to
its tracking page, never to the private token link), plus the visitor's
registration and demo requests and subscription payments with Vezano. Same
rules as the store page: exact matches, 90 days, 10 results, masked
contacts, one miss message, a shared per-address budget, no caching."""

import importlib
from datetime import timedelta
from decimal import Decimal

from django.apps import apps as global_apps
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from org.models import Company
from subscriptions.models import SubscriptionPayment
from website import tracking
from website.models import (
    PlatformLead, PublicOrder, PublicOrderEvent, PublicOrderLine, RegistrationRequest, Website,
)

URL = "/api/public/track/"
PHONE = "0912345678"


@override_settings(VEZANO_CANONICAL_HOST="vezano.app")
class PlatformTrackingTestBase(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.bakery = self._store("bakery", "مخبز النيل")
        self.shop = self._store("shop", "Shop Two")

    def _store(self, slug, name, *, published=True, active=True):
        company = Company.objects.create(
            name=name, slug=slug, currency="SDG", is_active=active,
        )
        return Website.objects.create(
            company=company, business_name=name, is_published=published, accept_orders=True,
        )

    def _order(self, site, *, name="أحمد علي محمد", email="", phone=PHONE, days_ago=0,
               address="شارع النيل، الخرطوم"):
        order = PublicOrder.objects.create(
            company=site.company, website=site,
            reference="W" + str(PublicOrder.objects.count() + 100000)[-6:].rjust(6, "A"),
            contact_name=name, phone=phone, email=email, delivery_mode=PublicOrder.DELIVERY,
            address=address, currency="SDG", total=Decimal("1000.00"), language="ar",
        )
        if days_ago:
            PublicOrder.objects.filter(pk=order.pk).update(
                created_at=timezone.now() - timedelta(days=days_ago)
            )
            order.refresh_from_db()
        PublicOrderLine.objects.create(
            order=order, name="Bread", quantity=Decimal("2"), unit_price=Decimal("500"),
        )
        PublicOrderEvent.objects.create(
            company=order.company, order=order, to_status=PublicOrder.NEW,
            created_at=order.created_at,
        )
        return order

    def _registration(self, **fields):
        data = {
            "company_name": "Northwind Trading", "contact_name": "Amina Owner",
            "email": "amina@northwind.test", "phone": "+249 912 345 678", "country": "SD",
            "privacy_version": "2026-09",
        }
        data.update(fields)
        return RegistrationRequest.objects.create(**data)

    def _search(self, query, language="ar", ip="10.0.0.1"):
        return self.client.post(
            URL, {"q": query, "language": language}, format="json", REMOTE_ADDR=ip,
        )

    def _results(self, query, **kwargs):
        response = self._search(query, **kwargs)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["results"]


class CrossStoreOrderTests(PlatformTrackingTestBase):
    def test_reference_finds_an_order_in_any_store_labelled_with_the_store(self):
        order = self._order(self.shop, email="ahmed@example.com")
        results = self._results(order.reference.lower())
        self.assertEqual(len(results), 1)
        item = results[0]
        self.assertEqual(item["kind"], "order")
        self.assertEqual(item["reference"], order.reference)
        self.assertEqual(item["store_name"], "Shop Two")
        self.assertEqual(item["store_track_path"], "/s/shop/track/")
        self.assertEqual(item["customer"], "أحمد")  # first name for a reference

    def test_phone_email_and_name_find_orders_across_stores_masked(self):
        first = self._order(self.bakery, email="Amal@Example.com", name="Amal Hassan")
        second = self._order(self.shop, email="amal@example.com", name="Amal Hassan")
        for query in ("amal@EXAMPLE.com", "+249 912-345-678", "٠٩١٢٣٤٥٦٧٨", " amal   hassan "):
            response = self._search(query)
            results = response.json()["results"]
            self.assertEqual(
                {item["reference"] for item in results}, {first.reference, second.reference},
                query,
            )
            self.assertEqual({item["store_name"] for item in results}, {"مخبز النيل", "Shop Two"})
            for item in results:
                self.assertEqual(item["customer"], "A. H.")
            body = response.content.decode()
            for secret in ("Amal Hassan", "amal@example.com", "Amal@Example.com", PHONE,
                           "912345678", "شارع النيل"):
                self.assertNotIn(secret, body, query)

    def test_no_private_token_link_ever(self):
        order = self._order(self.bakery, email="x@example.com")
        for query in (order.reference, "x@example.com", PHONE, "أحمد علي محمد"):
            body = self._search(query).content.decode()
            self.assertIn(order.reference, body)
            self.assertNotIn(order.tracking_token, body)
            self.assertNotIn("/track/" + order.tracking_token, body)

    def test_unpublished_or_inactive_stores_are_left_out(self):
        hidden = self._store("hidden", "Hidden", published=False)
        closed = self._store("closed", "Closed", active=False)
        self._order(hidden, email="a@example.com")
        self._order(closed, email="a@example.com")
        self.assertEqual(self._results("a@example.com"), [])

    def test_only_the_last_90_days(self):
        self._order(self.bakery, email="old@example.com", days_ago=tracking.LOOKUP_DAYS + 1)
        recent = self._order(self.bakery, email="old@example.com", days_ago=3)
        self.assertEqual(
            [item["reference"] for item in self._results("old@example.com")], [recent.reference]
        )

    def test_at_most_ten_results_in_all_newest_first(self):
        for index in range(7):
            self._order(self.bakery if index % 2 else self.shop, email="many@example.com",
                        days_ago=index + 1)
        for index in range(6):
            self._order(self.shop, email="many@example.com", days_ago=index + 10)
        results = self._results("many@example.com")
        self.assertEqual(len(results), tracking.LOOKUP_LIMIT)
        stamps = [item["created_at"] for item in results]
        self.assertEqual(stamps, sorted(stamps, reverse=True))

    def test_misses_read_the_same_and_are_not_cached_or_indexed(self):
        self._order(self.bakery, email="a@example.com")
        answers = set()
        for query in ("WZZZZZZ", "RZZZZZZ", "nobody@example.com", "0999999999", "No One"):
            response = self._search(query)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Cache-Control"], "no-store")
            self.assertEqual(response["X-Robots-Tag"], "noindex")
            answers.add(response.content)
        self.assertEqual(len(answers), 1)

    def test_rate_limit_is_shared_with_the_store_page(self):
        for _index in range(tracking.RATE_LIMIT):
            self.client.post("/s/bakery/track/", {"q": "nobody@example.com"},
                             REMOTE_ADDR="10.0.0.9")
        response = self._search("nobody@example.com", ip="10.0.0.9")
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json(), {"limited": True, "results": []})
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(self._search("nobody@example.com", ip="10.0.0.10").status_code, 200)

    def test_empty_query_is_refused_and_get_is_not_allowed(self):
        self.assertEqual(self._search("  ").status_code, 400)
        self.assertEqual(self.client.get(URL).status_code, 405)

    def test_query_never_logged(self):
        self._order(self.bakery, email="secret@example.com")
        with self.assertLogs("website.platform_tracking", "INFO") as logs:
            self._search("secret@example.com")
        text = "\n".join(logs.output)
        self.assertIn("kind=email hits=1 order=1", text)
        self.assertNotIn("secret", text)

    def test_english_labels(self):
        order = self._order(self.bakery)
        item = self._results(order.reference, language="en")[0]
        self.assertEqual(item["status_label"], "Received")


class PlatformRequestTests(PlatformTrackingTestBase):
    def test_trial_and_demo_requests_never_show_in_the_open_search(self):
        """Since 2026-10-01 they open only with an email code
        (website.test_request_tracking); here every key reads as a miss."""
        row = self._registration()
        lead = PlatformLead.objects.create(
            name="Sara Musa", phone="0912 345 678", email="sara@example.test",
        )
        for query in (row.public_reference, row.public_reference.lower(), lead.public_reference,
                      "AMINA@northwind.test", "sara@example.test", "0912345678",
                      "amina  owner", "northwind trading", "sara musa"):
            response = self._search(query)
            self.assertEqual(response.status_code, 200, query)
            self.assertEqual(response.json()["results"], [], query)
            body = response.content.decode()
            for secret in (row.public_reference, lead.public_reference, "N. T.", "S. M."):
                self.assertNotIn(secret, body, query)

    def test_subscription_payment_by_full_transfer_reference_only(self):
        company = Company.objects.create(name="Blue Nile Stores", slug="bns", currency="SDG")
        owner = User.objects.create_user(
            email="o@bns.test", password="Owner-passw0rd!x", company=company,
        )
        payment = SubscriptionPayment.objects.create(
            company=company, amount=Decimal("20000"), currency="SDG", method="bank_transfer",
            reference_last4="7788", transfer_reference="TX20260011227788", recorded_by=owner,
            status=SubscriptionPayment.REJECTED, rejection_reason="Amount does not match",
        )
        results = self._results("tx-2026-0011-2277-88")
        self.assertEqual(len(results), 1)
        item = results[0]
        self.assertEqual(item["kind"], "subscription_payment")
        self.assertEqual(item["reference"], "…7788")
        self.assertEqual(item["customer"], "B. N. S.")
        self.assertEqual(item["reason"], "Amount does not match")
        self.assertNotIn(payment.transfer_reference, self._search("TX20260011227788").content
                         .decode())
        self.assertEqual(self._results("7788"), [])  # never by the last digits


class ReferenceBackfillTests(TestCase):
    def test_existing_requests_get_references_and_lookup_keys(self):
        row = RegistrationRequest.objects.create(
            company_name="مؤسسة الإخاء", contact_name="أحمد", email="a@example.test",
            phone="0912345678", country="SD", privacy_version="2026-09",
        )
        lead = PlatformLead.objects.create(name="Visitor", phone="+249 91 234 5678")
        RegistrationRequest.objects.filter(pk=row.pk).update(
            public_reference=None, lookup_name="", lookup_company="", lookup_phone="",
        )
        PlatformLead.objects.filter(pk=lead.pk).update(
            public_reference=None, lookup_name="", lookup_phone="",
        )
        migration = importlib.import_module(
            "website.migrations.0019_backfill_platform_request_tracking"
        )
        migration.backfill(global_apps, None)
        row.refresh_from_db()
        lead.refresh_from_db()
        self.assertRegex(row.public_reference, r"^R[A-Z0-9]{6}$")
        self.assertEqual(row.lookup_company, tracking.name_key("مؤسسة الاخاء"))
        self.assertEqual(row.lookup_phone, "912345678")
        self.assertRegex(lead.public_reference, r"^D[A-Z0-9]{6}$")
        self.assertEqual(lead.lookup_phone, "912345678")

    def test_reference_is_kept_across_saves(self):
        lead = PlatformLead.objects.create(name="Visitor", email="v@example.test")
        reference = lead.public_reference
        lead.status = PlatformLead.STATUS_CONTACTED
        lead.save(update_fields=["status"])
        lead.refresh_from_db()
        self.assertEqual(lead.public_reference, reference)


class TrackPageExportTests(TestCase):
    def test_marketing_track_page_is_noindex_when_built(self):
        from core.frontend import FRONTEND_DIST

        page = FRONTEND_DIST / "track" / "index.html"
        if not page.is_file():
            self.skipTest("frontend/out is not built")
        html = page.read_text(encoding="utf-8")
        self.assertIn('name="robots" content="noindex', html)
        self.assertNotIn("/track/", (FRONTEND_DIST / "sitemap.xml").read_text(encoding="utf-8"))
