"""Security review 2 (2026-09-28): the public surface answers malformed
input with 400 (not 500), a company suspended until payment keeps its page
but takes no orders or transfer claims, archived products leave the page,
and push subscriptions only point at real push services."""

import tempfile
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Role, User
from core.push import is_push_endpoint
from inventory.models import Product
from org.models import Branch, Company
from sales.models import CompanyBankAccount
from subscriptions.models import Plan, PlanVersion, Subscription
from website.models import (
    FeaturedProduct, PublicOrder, PublicOrderPayment, PushSubscription, Website,
)

MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA)
class PublicSurfaceBase(TestCase):
    def setUp(self):
        cache.clear()
        self.company = Company.objects.create(name="Bakery", slug="bakery", currency="SDG")
        self.branch = Branch.objects.create(
            company=self.company, name="Main", phone="+249900000001"
        )
        self.site = Website.objects.create(
            company=self.company, business_name="Bakery", is_published=True,
            accept_orders=True, contact_phone="+249900000000",
        )
        self.bread = Product.objects.create(
            company=self.company, sku="BR", name="Bread", sale_price=Decimal("500"),
            is_stock_tracked=False,
        )
        FeaturedProduct.objects.create(
            company=self.company, website=self.site, product=self.bread, show_price=True,
        )
        self.bank = CompanyBankAccount.objects.create(
            company=self.company, bank_name="BoK", account_name="Bakery", account_number="1",
            show_to_customers=True,
        )
        self.client = APIClient(raise_request_exception=False)

    def order(self, **extra):
        body = {"contact_name": "Amal Hassan", "phone": "0912345678",
                "lines": [{"product": self.bread.pk, "quantity": 1}]}
        body.update(extra)
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post("/api/public/site/bakery/orders/", body, format="json")

    def claim(self, reference, **extra):
        body = {"bank_account": self.bank.pk, "sender_bank_name": "X",
                "reference_last4": "1234", "amount": "500"}
        body.update(extra)
        return self.client.post(
            f"/api/public/site/bakery/orders/{reference}/", body, format="json"
        )


class MalformedInputTests(PublicSurfaceBase):
    def test_a_line_that_is_not_an_object(self):
        self.assertEqual(self.order(lines=["x"]).status_code, 400)

    def test_a_quantity_that_is_not_a_number(self):
        for quantity in ("NaN", "Infinity", "-Infinity"):
            response = self.order(lines=[{"product": self.bread.pk, "quantity": quantity}])
            self.assertEqual(response.status_code, 400, quantity)

    def test_a_branch_that_is_not_a_number(self):
        self.assertEqual(self.order(branch="abc").status_code, 400)

    def test_a_json_array_body(self):
        for url in ("/api/public/site/bakery/orders/", "/api/public/track/"):
            self.assertEqual(self.client.post(url, [1], format="json").status_code, 400, url)
        reference = self.order().data["reference"]
        response = self.client.post(
            f"/api/public/site/bakery/orders/{reference}/", [1], format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_a_claimed_amount_that_is_not_a_number(self):
        reference = self.order().data["reference"]
        for amount in ("NaN", "sNaN", "Infinity"):
            self.assertEqual(self.claim(reference, amount=amount).status_code, 400, amount)
        self.assertFalse(PublicOrderPayment.objects.exists())

    def test_a_well_formed_order_still_lands(self):
        response = self.order()
        self.assertEqual(response.status_code, 201, response.data)


class SuspendedShopTests(PublicSurfaceBase):
    def setUp(self):
        super().setUp()
        plan = Plan.objects.create(code="b", name="B")
        version = PlanVersion.objects.create(
            plan=plan, version=1, currency="SDG", price=Decimal("1"),
            billing_cycle=PlanVersion.MONTHLY, modules=["*"], published_at=timezone.now(),
        )
        now = timezone.now()
        self.subscription = Subscription.objects.create(
            company=self.company, plan_version=version, status=Subscription.ACTIVE,
            starts_at=now - timedelta(days=40), period_ends_at=now + timedelta(days=2),
        )

    def _suspend(self):
        Subscription.objects.filter(pk=self.subscription.pk).update(
            status=Subscription.SUSPENDED, suspension_kind=Subscription.SUSPENSION_UNPAID,
            suspended_at=timezone.now(), suspended_reason="unpaid",
        )

    @override_settings(
        EMAIL_ENABLED=True, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    )
    def test_the_page_stays_but_orders_are_refused_with_the_reason(self):
        self._suspend()
        response = self.order(email="amal@example.test")
        self.assertEqual(response.status_code, 400)
        self.assertIn("المتجر لا يستقبل طلبات حاليًا", str(response.data))
        self.assertFalse(PublicOrder.objects.exists())
        self.assertEqual(len(mail.outbox), 0)
        page = self.client.get("/s/bakery/")
        self.assertEqual(page.status_code, 200)
        html = page.content.decode()
        # The fixture page reads as English; an Arabic one says
        # «المتجر لا يستقبل طلبات حاليًا».
        self.assertIn("The shop is not taking orders right now", html)
        self.assertNotIn('id="order"', html)
        self.assertNotIn("data-add=", html)
        api = self.client.get("/api/public/site/bakery/").data
        self.assertFalse(api["accept_orders"])
        self.assertTrue(api["orders_paused"])

    def test_transfer_claims_are_refused_and_the_pay_page_says_why(self):
        reference = self.order().data["reference"]
        order = PublicOrder.objects.get(reference=reference)
        self.assertTrue(self.client.get(f"/api/public/site/bakery/orders/{reference}/")
                        .data["can_pay"])
        self._suspend()
        status_view = self.client.get(f"/api/public/site/bakery/orders/{reference}/").data
        self.assertFalse(status_view["can_pay"])
        self.assertTrue(status_view["orders_paused"])
        with mock.patch("core.push.send_to_user") as push:
            response = self.claim(reference)
        self.assertEqual(response.status_code, 400)
        self.assertIn("المتجر لا يستقبل طلبات حاليًا", str(response.data))
        push.assert_not_called()
        self.assertFalse(order.payments.exists())
        pay = self.client.get(f"/s/bakery/pay/?ref={reference}")
        self.assertEqual(pay.status_code, 200)
        self.assertIn("The shop is not taking orders right now", pay.content.decode())

    def test_an_active_company_is_untouched(self):
        self.assertEqual(self.order().status_code, 201)
        self.assertTrue(self.client.get("/api/public/site/bakery/").data["accept_orders"])


class ArchivedProductTests(PublicSurfaceBase):
    def test_a_deactivated_product_leaves_the_page(self):
        self.bread.is_active = False
        self.bread.save()
        featured = self.client.get("/api/public/site/bakery/").data["featured_products"]
        self.assertEqual(featured, [])
        self.assertNotIn("Bread", self.client.get("/s/bakery/").content.decode())


class ClaimLookupTests(PublicSurfaceBase):
    def test_a_missing_claim_is_404(self):
        reference = self.order().data["reference"]
        order = PublicOrder.objects.get(reference=reference)
        role = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        owner = User.objects.create_user(
            email="owner@bakery.test", password="Owner-passw0rd!x", company=self.company,
            role=role,
        )
        staff = APIClient(raise_request_exception=False)
        staff.force_authenticate(owner)
        for path in ("proof/", "confirm/", "reject/"):
            method = staff.get if path == "proof/" else staff.post
            response = method(f"/api/web-orders/{order.pk}/payments/999999/{path}")
            self.assertEqual(response.status_code, 404, path)


PUSH = {"WEB_PUSH_ENABLED": True, "VAPID_PRIVATE_KEY": "priv", "VAPID_PUBLIC_KEY": "pub"}


@override_settings(**PUSH)
class PushEndpointTests(TestCase):
    def setUp(self):
        company = Company.objects.create(name="Bakery", slug="bakery")
        role = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        self.user = User.objects.create_user(
            email="owner@bakery.test", password="Owner-passw0rd!x", company=company, role=role,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def subscribe(self, endpoint):
        return self.client.post("/api/push/subscription/", {
            "endpoint": endpoint, "keys": {"p256dh": "k", "auth": "a"},
        }, format="json")

    def test_real_push_services_are_accepted(self):
        for endpoint in (
            "https://fcm.googleapis.com/fcm/send/abc",
            "https://updates.push.services.mozilla.com/wpush/v2/abc",
            "https://wns2-par02p.notify.windows.com/w/?token=abc",
            "https://web.push.apple.com/QGx",
            "https://api.push.apple.com/3/device/abc",
        ):
            self.assertEqual(self.subscribe(endpoint).status_code, 201, endpoint)

    def test_anything_else_is_refused(self):
        for endpoint in (
            "https://169.254.169.254/latest/meta-data/",
            "https://localhost/x", "http://fcm.googleapis.com/fcm/send/abc",
            "https://fcm.googleapis.com.evil.test/x", "https://evil.test/fcm.googleapis.com",
            "https://user:pw@fcm.googleapis.com/x", "https://fcm.googleapis.com:8443/x",
            "https://notify.windows.com.evil.test/x",
        ):
            self.assertEqual(self.subscribe(endpoint).status_code, 400, endpoint)
        self.assertFalse(PushSubscription.objects.exists())

    def test_a_stored_endpoint_off_the_list_is_never_called(self):
        from core import push

        PushSubscription.objects.create(
            user=self.user, company_id=self.user.company_id,
            endpoint="https://internal.example/hook", p256dh="k", auth="a",
        )
        with mock.patch("pywebpush.webpush") as webpush:
            push.send_to_user(self.user, title="t", body="b")
        webpush.assert_not_called()
        self.assertFalse(PushSubscription.objects.exists())

    def test_helper(self):
        self.assertTrue(is_push_endpoint("https://fcm.googleapis.com/fcm/send/1"))
        self.assertFalse(is_push_endpoint("https://[::1]/x"))
        self.assertFalse(is_push_endpoint(None))


class ContentSecurityPolicyTests(PublicSurfaceBase):
    def test_company_page_carries_the_policy(self):
        page = self.client.get("/s/bakery/")
        self.assertEqual(page.status_code, 200)
        policy = page["Content-Security-Policy"]
        self.assertIn("default-src 'self'", policy)
        self.assertIn("object-src 'none'", policy)
        self.assertIn("frame-ancestors 'none'", policy)
        self.assertIn("https://fonts.googleapis.com", policy)
        strict = page["Content-Security-Policy-Report-Only"]
        self.assertIn("'sha256-", strict)
        script_src = strict.split("script-src ", 1)[1].split(";", 1)[0]
        self.assertNotIn("unsafe-inline", script_src)

    def test_json_api_is_left_alone(self):
        response = self.client.get("/api/public/site/bakery/")
        self.assertNotIn("Content-Security-Policy", response)
