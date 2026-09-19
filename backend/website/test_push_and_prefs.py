"""P2 of public orders: push to the shop's browsers, who is told, and the
visit → order numbers."""

from decimal import Decimal
from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import Role, User
from inventory.models import Product
from org.models import Branch, Company
from website.models import FeaturedProduct, PublicOrder, PushSubscription, Website

PUSH = {
    "WEB_PUSH_ENABLED": True, "VAPID_PRIVATE_KEY": "priv", "VAPID_PUBLIC_KEY": "pub",
    "EMAIL_ENABLED": True, "EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend",
}


@override_settings(**PUSH)
class PushAndPrefsTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Bakery", slug="bakery")
        self.branch = Branch.objects.create(company=self.company, name="North")
        owner_role = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        manager_role = Role.objects.create(name="Branch Manager", scope_level=Role.SCOPE_BRANCH)
        self.owner = User.objects.create_user(
            email="owner@bakery.test", password="Owner-passw0rd!x", company=self.company,
            role=owner_role,
        )
        self.manager = User.objects.create_user(
            email="north@bakery.test", password="Mgr-passw0rd!x", company=self.company,
            role=manager_role, branch=self.branch,
        )
        self.site = Website.objects.create(
            company=self.company, business_name="Bakery", is_published=True, accept_orders=True,
        )
        self.bread = Product.objects.create(
            company=self.company, sku="BR", name="Bread", sale_price=Decimal("500"),
            is_stock_tracked=False,
        )
        FeaturedProduct.objects.create(company=self.company, website=self.site, product=self.bread)

    def _subscribe(self, user, endpoint):
        client = APIClient()
        client.force_authenticate(user)
        return client.post(
            "/api/push/subscription/",
            {"endpoint": endpoint, "keys": {"p256dh": "k", "auth": "a"}}, format="json",
        )

    def _order(self):
        with self.captureOnCommitCallbacks(execute=True):
            return APIClient().post(
                "/api/public/site/bakery/orders/",
                {"contact_name": "Amal", "phone": "0912345678", "branch": self.branch.pk,
                 "lines": [{"product": self.bread.pk, "quantity": 1}]},
                format="json",
            )

    def test_subscription_lifecycle_and_public_key(self):
        client = APIClient()
        client.force_authenticate(self.manager)
        info = client.get("/api/push/subscription/")
        self.assertEqual(info.data, {"enabled": True, "public_key": "pub", "subscriptions": 0})
        self.assertEqual(self._subscribe(self.manager, "https://push.example/1").status_code, 201)
        # Same endpoint again: one row, updated.
        self.assertEqual(self._subscribe(self.manager, "https://push.example/1").status_code, 201)
        self.assertEqual(PushSubscription.objects.count(), 1)
        bad = client.post(
            "/api/push/subscription/", {"endpoint": "http://x", "keys": {}}, format="json"
        )
        self.assertEqual(bad.status_code, 400)
        gone = client.delete(
            "/api/push/subscription/", {"endpoint": "https://push.example/1"}, format="json"
        )
        self.assertEqual(gone.status_code, 204)
        self.assertEqual(PushSubscription.objects.count(), 0)

    @override_settings(WEB_PUSH_ENABLED=False)
    def test_disabled_push_reports_and_refuses(self):
        client = APIClient()
        client.force_authenticate(self.manager)
        self.assertFalse(client.get("/api/push/subscription/").data["enabled"])
        self.assertEqual(self._subscribe(self.manager, "https://push.example/1").status_code, 503)

    def test_new_order_pushes_and_emails_the_right_people(self):
        self._subscribe(self.manager, "https://push.example/m")
        self._subscribe(self.owner, "https://push.example/o")
        self.site.order_notify_owners = False
        self.site.order_notify_emails = "accounts@bakery.test\nnot an email\n"
        self.site.save()
        with mock.patch("pywebpush.webpush") as webpush:
            response = self._order()
        self.assertEqual(response.status_code, 201, response.data)
        # Push: the branch manager only (owners switched off).
        endpoints = [c.kwargs["subscription_info"]["endpoint"] for c in webpush.call_args_list]
        self.assertEqual(endpoints, ["https://push.example/m"])
        payload = webpush.call_args_list[0].kwargs["data"]
        self.assertIn(response.data["reference"], payload)
        self.assertIn("/web-orders/?ref=", payload)
        # Email: the manager and the extra address; the junk line ignored.
        told = sorted(m.to[0] for m in mail.outbox)
        self.assertEqual(told, ["accounts@bakery.test", "north@bakery.test"])

    def test_owners_are_told_too_when_the_site_says_so(self):
        self.site.order_notify_owners = True
        self.site.save()
        with mock.patch("pywebpush.webpush"):
            self._order()
        told = sorted(m.to[0] for m in mail.outbox)
        self.assertEqual(told, ["north@bakery.test", "owner@bakery.test"])

    def test_dead_endpoint_is_forgotten(self):
        from pywebpush import WebPushException

        from core import push

        self._subscribe(self.manager, "https://push.example/dead")
        response = mock.Mock(status_code=410)
        boom = WebPushException("gone", response=response)
        with mock.patch("pywebpush.webpush", side_effect=boom):
            delivered = push.send_to_user(self.manager, title="t", body="b")
        self.assertEqual(delivered, 0)
        self.assertEqual(PushSubscription.objects.count(), 0)

    def test_company_visits_report_orders(self):
        with mock.patch("pywebpush.webpush"):
            self._order()
        client = APIClient()
        client.force_authenticate(self.owner)
        data = client.get("/api/website/visits/").data
        self.assertEqual(data["orders"], 1)
        self.assertEqual(data["orders_confirmed"], 0)
        PublicOrder.objects.update(status=PublicOrder.CONFIRMED)
        self.assertEqual(client.get("/api/website/visits/").data["orders_confirmed"], 1)
